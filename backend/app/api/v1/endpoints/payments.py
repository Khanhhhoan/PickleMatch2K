import hmac
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.api.permissions import managed_venue_ids, require_booking_staff
from app.core.config import settings
from app.models.booking import Booking
from app.models.payment import PaymentTransaction
from app.models.user import User, UserRole
from app.schemas.payment import (
    CheckoutResponse,
    PaymentConfigResponse,
    PaymentTransactionResponse,
    SepayWebhookPayload,
)
from app.services import booking_service, ledger, payment_service

router = APIRouter()
logger = logging.getLogger("pickleball.sepay")

MANAGER_ROLES = (UserRole.ADMIN.value, UserRole.OWNER.value, UserRole.STAFF.value)


def _get_accessible_booking(db: Session, booking_id: int, user: User) -> Booking:
    """Đơn mà người dùng được phép xem thanh toán: chủ đơn, hoặc người quản lý cụm sân của đơn."""
    booking = booking_service.get_booking_or_404(db, booking_id)
    if booking.user_id == user.id:
        return booking
    if user.role in MANAGER_ROLES:
        require_booking_staff(db, user, booking)
        return booking
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy đơn đặt sân")


@router.get("/config", response_model=PaymentConfigResponse)
def get_payment_config():
    """Cấu hình công khai cho giao diện (ví dụ: có hiện nút giả lập thanh toán hay không)."""
    return PaymentConfigResponse(
        simulator_enabled=settings.SEPAY_SIMULATOR_ENABLED,
        unified_account_mode=settings.SEPAY_UNIFIED_TEST_MODE,
    )


@router.get("/checkout/{booking_id}", response_model=CheckoutResponse)
def get_checkout(
    booking_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Thông tin chuyển khoản và mã VietQR để thanh toán cọc cho một đơn."""
    booking = _get_accessible_booking(db, booking_id, current_user)
    return payment_service.get_checkout_info(db, booking)


def _verify_webhook_key(authorization: Optional[str]) -> None:
    expected = settings.SEPAY_WEBHOOK_API_KEY
    if not expected:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Webhook chưa được cấu hình khóa xác thực (SEPAY_WEBHOOK_API_KEY).",
            )
        return  # môi trường phát triển: cho phép, đã cảnh báo lúc khởi động
    provided = (authorization or "").strip()
    for prefix in ("Apikey ", "Bearer "):
        if provided.startswith(prefix):
            provided = provided[len(prefix):].strip()
            break
    if not hmac.compare_digest(provided.encode(), expected.strip().encode()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Khóa xác thực webhook không hợp lệ.")


@router.post("/sepay-webhook")
def sepay_webhook(
    payload: SepayWebhookPayload,
    db: Session = Depends(deps.get_db),
    authorization: Optional[str] = Header(None),
):
    """SePay gọi vào đây mỗi khi tài khoản nhận có giao dịch. Header: `Authorization: Apikey <KEY>`."""
    _verify_webhook_key(authorization)
    return payment_service.process_sepay_webhook(db, payload)


@router.post("/simulate-sepay/{booking_id}")
def simulate_payment(
    booking_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Giả lập SePay báo đã nhận tiền cọc. Chỉ hoạt động khi SEPAY_SIMULATOR_ENABLED=true (demo/kiểm thử)."""
    if not settings.SEPAY_SIMULATOR_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tính năng giả lập thanh toán đang tắt.")
    booking = _get_accessible_booking(db, booking_id, current_user)
    return payment_service.simulate_sepay_payment(db, booking)


@router.get("/transactions", response_model=List[PaymentTransactionResponse])
def get_payment_transactions(
    owner_id: Optional[int] = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Sổ giao dịch: Admin xem tất cả (lọc theo chủ sân), chủ sân/nhân viên xem của cụm sân mình, người chơi xem của mình."""
    query = db.query(PaymentTransaction).options(joinedload(PaymentTransaction.booking))

    if current_user.role in MANAGER_ROLES:
        venue_ids = managed_venue_ids(db, current_user)
        if current_user.role == UserRole.ADMIN.value and owner_id:
            from app.models.venue import Venue

            venue_ids = [row[0] for row in db.query(Venue.id).filter(Venue.owner_id == owner_id).all()]
        if venue_ids is not None:
            if not venue_ids:
                return []
            booking_ids = ledger.venue_booking_ids_subquery(db, venue_ids)
            query = query.filter(PaymentTransaction.booking_id.in_(db.query(booking_ids.c.booking_id)))
    else:
        my_bookings = db.query(Booking.id).filter(Booking.user_id == current_user.id)
        query = query.filter(PaymentTransaction.booking_id.in_(my_bookings))

    return query.order_by(PaymentTransaction.id.desc()).limit(500).all()
