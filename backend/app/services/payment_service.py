import logging
import re
import urllib.parse
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.websocket_manager import dispatch, manager
from app.models.booking import Booking, BookingStatus
from app.models.payment import PaymentKind, PaymentMethod
from app.schemas.payment import CheckoutResponse, SepayWebhookPayload
from app.services import booking_service, ledger
from app.utils.timeutils import as_utc, now_utc

logger = logging.getLogger("pickleball.sepay")

BANK_CODE_MAP = {
    "techcombank": ("Techcombank", "TCB"), "tcb": ("Techcombank", "TCB"),
    "vietcombank": ("Vietcombank", "VCB"), "vcb": ("Vietcombank", "VCB"),
    "vietinbank": ("VietinBank", "CTG"), "ctg": ("VietinBank", "CTG"),
    "sacombank": ("Sacombank", "STB"), "stb": ("Sacombank", "STB"),
    "mbbank": ("MBBank", "MB"), "mb": ("MBBank", "MB"),
    "vpbank": ("VPBank", "VPB"), "vpb": ("VPBank", "VPB"),
    "tpbank": ("TPBank", "TPB"), "tpb": ("TPBank", "TPB"),
    "bidv": ("BIDV", "BIDV"),
    "acb": ("ACB", "ACB"),
    "vib": ("VIB", "VIB"),
}


@dataclass(frozen=True)
class ReceivingAccount:
    account_number: str
    bank_name: str
    bank_code: str
    holder: str


def parse_owner_bank_info(raw: Optional[str]) -> Optional[tuple]:
    """
    Tách (số tài khoản, tên ngân hàng, mã ngân hàng) từ chuỗi chủ sân nhập, ví dụ
    '0765883535 - Techcombank (Van Anh)' hoặc '0901234567 (MBBank)'. Trả về None nếu không nhận diện được.
    """
    if not raw or not raw.strip():
        return None
    account = re.search(r"(\d{6,})", raw)
    lowered = raw.lower()
    bank = next((BANK_CODE_MAP[k] for k in sorted(BANK_CODE_MAP, key=len, reverse=True) if k in lowered), None)
    if not account or not bank:
        return None
    return account.group(1), bank[0], bank[1]


def resolve_receiving_account(booking: Booking) -> ReceivingAccount:
    """Tài khoản nhận tiền cọc của một đơn. Báo lỗi rõ ràng thay vì dùng tài khoản mặc định ngầm."""
    if settings.SEPAY_UNIFIED_TEST_MODE:
        if not (settings.SEPAY_BANK_ACCOUNT and settings.SEPAY_BANK_CODE):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Hệ thống chưa cấu hình tài khoản nhận thanh toán (SEPAY_BANK_ACCOUNT, SEPAY_BANK_CODE).",
            )
        return ReceivingAccount(
            settings.SEPAY_BANK_ACCOUNT, settings.SEPAY_BANK_NAME or settings.SEPAY_BANK_CODE,
            settings.SEPAY_BANK_CODE, settings.SEPAY_ACCOUNT_HOLDER,
        )

    venue = booking.details[0].court.venue if booking.details and booking.details[0].court else None
    profile = venue.owner.owner_profile if venue and venue.owner else None
    parsed = parse_owner_bank_info(profile.bank_account) if profile else None
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chủ sân chưa cấu hình tài khoản ngân hàng nhận tiền cọc. Vui lòng liên hệ cụm sân.",
        )
    holder = (profile.company_name or profile.full_name or "").strip()
    return ReceivingAccount(parsed[0], parsed[1], parsed[2], holder)


def generate_sepay_qr_url(bank_account: str, bank_code: str, amount: float, transfer_content: str) -> str:
    query = urllib.parse.urlencode({"acc": bank_account, "bank": bank_code, "amount": int(amount), "des": transfer_content})
    return f"https://qr.sepay.vn/img?{query}"


def get_checkout_info(db: Session, booking: Booking) -> CheckoutResponse:
    account = resolve_receiving_account(booking)
    total = float(booking.total_price)
    deposit = float(booking.deposit_amount or 0)
    paid = float(booking.paid_amount or 0)
    amount_due = max(0.0, deposit - paid)  # phần cọc còn thiếu
    transfer_content = booking.booking_code or f"PKL {booking.id}"

    expires_at = as_utc(booking.expires_at)
    remaining_secs = max(0, int((expires_at - now_utc()).total_seconds())) if expires_at else 0
    venue_name = booking.details[0].venue_name if booking.details else ""

    return CheckoutResponse(
        booking_id=booking.id,
        booking_code=booking.booking_code,
        status=booking.status,
        total_price=total,
        deposit_amount=deposit,
        paid_amount=paid,
        amount_due=amount_due,
        remaining_amount=max(0.0, total - max(paid, deposit)),
        deposit_percentage=50,
        payment_status=booking.payment_status or "UNPAID",
        venue_name=venue_name,
        bank_name=account.bank_name,
        bank_code=account.bank_code,
        bank_account_number=account.account_number,
        account_holder_name=account.holder,
        transfer_content=transfer_content,
        qr_code_url=generate_sepay_qr_url(account.account_number, account.bank_code, amount_due or deposit, transfer_content),
        expires_in_seconds=remaining_secs,
        simulator_enabled=settings.SEPAY_SIMULATOR_ENABLED,
    )


def find_booking_by_transfer_content(db: Session, content: str) -> Optional[Booking]:
    """Tìm đơn theo mã PK2K… trong nội dung chuyển khoản (chấp nhận cú pháp cũ 'PKL <id>')."""
    code = re.search(r"PK2K[\s_\-]*(\d{1,12})", content or "", re.IGNORECASE)
    if code:
        booking_code = f"PK2K{int(code.group(1)):06d}"
        booking = db.query(Booking).filter(Booking.booking_code == booking_code).first()
        if booking:
            return booking
    legacy = re.search(r"PKL[\s_\-]*(\d{1,12})", content or "", re.IGNORECASE)
    if legacy:
        return db.query(Booking).filter(Booking.id == int(legacy.group(1))).first()
    return None


def _notify_payment(booking: Booking, outcome: str) -> None:
    venue_id = booking.venue_id
    confirmed = outcome in ("confirmed", "reactivated")
    if venue_id and confirmed:
        dispatch(manager.broadcast_venue_event(venue_id, {
            "type": "PAYMENT_CONFIRMED",
            "venue_id": venue_id,
            "booking_id": booking.id,
            "status": booking.status,
            "payment_status": booking.payment_status,
            "message": "Một đơn đặt sân vừa được xác nhận thanh toán cọc.",
        }))
    dispatch(manager.broadcast_global({
        "type": "PAYMENT_CONFIRMED" if confirmed else "BOOKING_STATUS_CHANGED",
        "booking_id": booking.id,
        "venue_id": venue_id,
        "status": booking.status,
        "payment_status": booking.payment_status,
        "refund_status": booking.refund_status,
    }))


def process_sepay_webhook(db: Session, payload: SepayWebhookPayload) -> dict:
    """
    Xử lý một giao dịch SePay báo về:
    chỉ nhận tiền VÀO, khớp đơn theo mã trong nội dung, kiểm tra đúng tài khoản nhận,
    không ghi trùng cùng một mã tham chiếu, cộng dồn số tiền và cập nhật trạng thái đơn.
    """
    if payload.transferType and payload.transferType.lower() != "in":
        return {"status": "ignored", "reason": "Không phải giao dịch tiền vào"}

    content = payload.transactionContent or payload.content or payload.description or ""
    amount = float(payload.transferAmount or payload.amountIn or 0.0)
    reference = payload.referenceCode or payload.referenceNumber or (f"sepay-{payload.id}" if payload.id else None)
    if amount <= 0:
        return {"status": "ignored", "reason": "Số tiền không hợp lệ"}

    booking = find_booking_by_transfer_content(db, content)
    if not booking:
        logger.info("Webhook SePay không khớp đơn nào: %r", content)
        return {"status": "ignored", "reason": "Không tìm thấy mã đặt sân (PK2K...) trong nội dung chuyển khoản"}

    if payload.accountNumber:
        try:
            expected = resolve_receiving_account(booking).account_number
        except HTTPException:
            expected = None
        if expected and payload.accountNumber.strip() != expected:
            logger.warning("Webhook SePay sai tài khoản nhận cho đơn %s", booking.booking_code)
            return {"status": "ignored", "reason": "Tài khoản nhận không khớp với đơn đặt sân", "booking_id": booking.id}

    if ledger.find_by_reference(db, reference):
        return {"status": "success", "message": "Giao dịch đã được ghi nhận trước đó.", "booking_id": booking.id}

    booking = booking_service.get_booking_or_404(db, booking.id, for_update=True)
    try:
        ledger.record_transaction(
            db, booking, amount=amount, kind=PaymentKind.DEPOSIT.value, method=PaymentMethod.BANK_TRANSFER.value,
            gateway=payload.gateway or "SePay_VietQR", reference_number=reference, content=content,
            account_number=payload.accountNumber, raw_payload=payload.model_dump(),
        )
    except IntegrityError:
        # Hai webhook trùng mã tham chiếu đến cùng lúc: unique index chặn bản thứ hai
        db.rollback()
        return {"status": "success", "message": "Giao dịch đã được ghi nhận trước đó.", "booking_id": booking.id}

    outcome = booking_service.apply_payment(db, booking, amount)
    db.commit()
    db.refresh(booking)
    _notify_payment(booking, outcome)

    messages = {
        "confirmed": "Đã nhận đủ tiền cọc, đơn được xác nhận.",
        "reactivated": "Thanh toán đến muộn nhưng khung giờ còn trống, đơn được khôi phục và xác nhận.",
        "partial": f"Đã nhận {amount:,.0f}đ nhưng chưa đủ tiền cọc ({booking.deposit_amount:,.0f}đ).",
        "late_refund": "Thanh toán đến khi đơn không còn hiệu lực: đã tạo yêu cầu hoàn tiền.",
        "updated": "Đã ghi nhận khoản thanh toán bổ sung.",
        "recorded": "Đã ghi nhận giao dịch.",
    }
    return {
        "status": "success" if outcome in ("confirmed", "reactivated", "updated", "recorded") else "warning",
        "outcome": outcome,
        "message": messages[outcome],
        "booking_id": booking.id,
        "booking_status": booking.status,
        "payment_status": booking.payment_status,
        "amount_in": amount,
    }


def simulate_sepay_payment(db: Session, booking: Booking) -> dict:
    """Giả lập SePay báo có khoản chuyển đủ tiền cọc còn thiếu (chỉ dùng khi SEPAY_SIMULATOR_ENABLED)."""
    if booking.status not in (BookingStatus.PENDING.value, BookingStatus.EXPIRED.value):
        raise HTTPException(status_code=400, detail="Chỉ giả lập thanh toán cho đơn đang chờ cọc.")
    account = resolve_receiving_account(booking)
    due = max(0.0, float(booking.deposit_amount or 0) - float(booking.paid_amount or 0)) or float(booking.deposit_amount or 0)
    payload = SepayWebhookPayload(
        gateway="SePay_Simulator_VietQR",
        accountNumber=account.account_number,
        transferType="in",
        transferAmount=due,
        content=f"{booking.booking_code} chuyen khoan coc",
        referenceCode=f"SIM{uuid.uuid4().hex[:12].upper()}",
    )
    return process_sepay_webhook(db, payload)
