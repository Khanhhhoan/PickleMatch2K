import os
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import deps
from app.api.permissions import managed_venue_ids, require_booking_staff, require_court_staff
from app.core.booking_policy import SLOT_HOLD_SECONDS
from app.models.booking import Booking, BookingDetail, BookingSource, BookingStatus
from app.models.payment import PaymentKind, PaymentMethod, PaymentTransaction
from app.models.user import User, UserRole
from app.models.venue import Court, Venue
from app.schemas.booking import (
    BookingCreate,
    BookingResponse,
    BookingStatusUpdate,
    CancelBookingRequest,
    CancelPreviewResponse,
    CheckInRequest,
    CollectPaymentRequest,
    ConfirmRefundRequest,
    DeskBookingCreate,
    HoldSlotRequest,
    ReleaseSlotRequest,
    RescheduleRequest,
)
from app.services import booking_service, ledger, storage_service
from app.services.availability_service import is_valid_slot
from app.services.booking_service import SlotRequest
from app.services.slot_lock_service import slot_lock_manager
from app.utils.timeutils import today_vn, vn_day_bounds_utc

router = APIRouter()

venue_staff = deps.RoleChecker([UserRole.OWNER.value, UserRole.ADMIN.value, UserRole.STAFF.value])
admin_only = deps.RoleChecker([UserRole.ADMIN.value])


# ==========================================
# PLAYER
# ==========================================

@router.post("", response_model=BookingResponse)
def create_booking(
    booking_in: BookingCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Tạo đơn đặt sân (mỗi khung giờ 60 phút). Đơn ở trạng thái PENDING và giữ slot 15 phút
    để thanh toán cọc 50%; quá hạn đơn tự hết hiệu lực và slot được trả lại.
    """
    slots = [SlotRequest(d.court_id, d.date, d.start_time, d.end_time) for d in booking_in.details]
    return booking_service.create_booking(db, user=current_user, slots=slots)


@router.post("/hold-slot")
def hold_slot(
    payload: HoldSlotRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Giữ tạm một khung giờ trong 5 phút khi người chơi đang chọn slot."""
    court = db.query(Court).filter(Court.id == payload.court_id).first()
    if not court or court.venue_id != payload.venue_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy sân")
    if not is_valid_slot(court.venue, payload.date, payload.start_time, payload.end_time):
        raise HTTPException(status_code=400, detail="Khung giờ không hợp lệ.")

    success, message = slot_lock_manager.hold_slot(
        venue_id=court.venue_id,
        court_id=court.id,
        court_name=court.name,
        slot_date=str(payload.date),
        start_time=str(payload.start_time),
        end_time=str(payload.end_time),
        user_id=current_user.id,
    )
    if not success:
        raise HTTPException(status_code=409, detail=message)
    return {"status": "success", "message": message, "expire_in_seconds": SLOT_HOLD_SECONDS}


@router.post("/release-slot")
def release_slot(payload: ReleaseSlotRequest, current_user: User = Depends(deps.get_current_active_user)):
    released = slot_lock_manager.release_slot(
        payload.venue_id, payload.court_id, str(payload.date), str(payload.start_time), current_user.id
    )
    return {"status": "success", "released": released}


@router.get("/me", response_model=List[BookingResponse])
def get_my_bookings(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_active_user)):
    return booking_service.get_my_bookings(db, user_id=current_user.id)


@router.get("/{booking_id}/cancel-preview", response_model=CancelPreviewResponse)
def cancel_preview(
    booking_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Số tiền được hoàn nếu hủy ngay lúc này, theo chính sách hủy đã công bố."""
    booking = booking_service.get_booking_or_404(db, booking_id)
    if booking.user_id != current_user.id or booking.source != BookingSource.ONLINE.value:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn đặt sân")
    return booking_service.preview_cancellation(booking)


@router.post("/{booking_id}/cancel", response_model=BookingResponse)
@router.delete("/{booking_id}", response_model=BookingResponse)
def cancel_booking(
    booking_id: int,
    refund_info: Optional[CancelBookingRequest] = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Người chơi hủy đơn của chính mình. Tiền hoàn tính theo chính sách hủy."""
    return booking_service.cancel_by_player(db, booking_id, current_user, refund_info)


# ==========================================
# VENUE STAFF (chủ sân, nhân viên, admin)
# ==========================================

def _desk_booking(db: Session, payload: DeskBookingCreate, current_user: User, *, check_in_today: bool) -> Booking:
    court = require_court_staff(db, current_user, payload.court_id)
    slots = booking_service.split_into_hourly_slots(court.id, payload.date, payload.start_time, payload.end_time)

    if payload.payment_method in ("CASH", "BANK_TRANSFER"):
        paid, method = "FULL", payload.payment_method
    else:
        paid = {"FULLY_PAID": "FULL", "DEPOSIT_PAID": "DEPOSIT", "UNPAID": "NONE"}[payload.payment_method]
        method = PaymentMethod.CASH.value

    return booking_service.create_booking(
        db,
        user=current_user,
        slots=slots,
        source=BookingSource.DESK.value,
        guest_name=payload.customer_name,
        guest_phone=payload.customer_phone,
        desk_paid=paid,
        desk_method=method,
        price_override=payload.price or None,
        check_in_now=check_in_today and payload.date == today_vn(),
    )


@router.post("/desk", response_model=BookingResponse)
def create_desk_booking(
    payload: DeskBookingCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """Tạo đơn tại quầy cho khách gọi điện hoặc ghé sân đặt trước (đơn được xác nhận ngay)."""
    return _desk_booking(db, payload, current_user, check_in_today=False)


@router.post("/staff/walkin", response_model=BookingResponse)
def create_staff_walkin_booking(
    payload: DeskBookingCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """Khách vãng lai vào sân ngay: đơn trong ngày được ghi nhận là đã nhận sân."""
    return _desk_booking(db, payload, current_user, check_in_today=True)


def _get_staff_booking(db: Session, booking_id: int, current_user: User) -> Booking:
    booking = booking_service.get_booking_or_404(db, booking_id, for_update=True)
    require_booking_staff(db, current_user, booking)
    return booking


@router.post("/{booking_id}/checkin", response_model=BookingResponse)
def check_in_booking(
    booking_id: int,
    payload: Optional[CheckInRequest] = None,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """Khách đến nhận sân: ghi nhận check-in và khoản thu tại quầy (mặc định thu hết phần còn lại)."""
    payload = payload or CheckInRequest()
    booking = _get_staff_booking(db, booking_id, current_user)
    return booking_service.check_in(db, booking, current_user, payload.collected_amount, payload.payment_method)


@router.post("/{booking_id}/collect", response_model=BookingResponse)
def collect_booking_payment(
    booking_id: int,
    payload: CollectPaymentRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """Ghi nhận một khoản thu tại quầy: tiền cọc của đơn đang chờ, hoặc phần còn lại sau khi chơi."""
    booking = _get_staff_booking(db, booking_id, current_user)
    return booking_service.collect_payment(db, booking, current_user, payload.amount, payload.payment_method)


@router.post("/{booking_id}/confirm-refund", response_model=BookingResponse)
def confirm_refund(
    booking_id: int,
    payload: ConfirmRefundRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """
    Xác nhận đã chuyển tiền hoàn cho khách, kèm mã giao dịch ngân hàng của lần chuyển (bắt buộc).
    Hệ thống không tự chuyển tiền: nhân viên chuyển khoản thủ công rồi xác nhận ở đây.
    """
    booking = _get_staff_booking(db, booking_id, current_user)
    return booking_service.confirm_refund(db, booking, current_user, bank_reference=payload.bank_reference, note=payload.note)


@router.post("/{booking_id}/refund-proof", response_model=BookingResponse)
async def upload_refund_proof(
    booking_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """Đính kèm chứng từ chuyển hoàn (ảnh JPG/PNG/WEBP hoặc PDF, tối đa 5MB) cho đơn đã xác nhận hoàn tiền."""
    limit = storage_service.MAX_PROOF_BYTES
    contents = await file.read(limit + 1)
    booking = _get_staff_booking(db, booking_id, current_user)
    if booking.refund_status != "COMPLETED":
        raise HTTPException(status_code=400, detail="Chỉ đính kèm chứng từ cho đơn đã xác nhận hoàn tiền.")
    old = booking.refund_proof_file
    booking.refund_proof_file = storage_service.save_refund_proof(booking.id, contents)
    db.commit()
    if old:
        storage_service.delete_refund_proof(old)
    db.refresh(booking)
    return booking


@router.get("/{booking_id}/refund-proof")
def download_refund_proof(
    booking_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Tải chứng từ chuyển hoàn. Chỉ người quản lý cụm sân của đơn, quản trị viên và chính khách của đơn được xem."""
    booking = booking_service.get_booking_or_404(db, booking_id)
    if booking.user_id != current_user.id or booking.is_desk_booking:
        require_booking_staff(db, current_user, booking)
    if not booking.refund_proof_file:
        raise HTTPException(status_code=404, detail="Đơn này chưa có chứng từ hoàn tiền.")
    path, media_type = storage_service.refund_proof_path(booking.refund_proof_file)
    return FileResponse(path, media_type=media_type, filename=f"chung-tu-hoan-tien-{booking.booking_code}{os.path.splitext(path)[1]}")


@router.put("/{booking_id}/status", response_model=BookingResponse)
def update_booking_status(
    booking_id: int,
    status_update: BookingStatusUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """
    Chuyển trạng thái đơn theo đúng quy trình (không gán trạng thái tùy ý):
    CHECKED_IN = check-in và thu phần còn lại; COMPLETED = hoàn tất đơn đã check-in
    (đơn chưa check-in thì check-in trước); CANCELLED = cụm sân hủy và hoàn tiền đã trả.
    """
    booking = _get_staff_booking(db, booking_id, current_user)
    target = status_update.status
    if target == "CANCELLED":
        return booking_service.cancel_by_venue(db, booking, current_user, status_update.reason)
    if target == "CHECKED_IN" or booking.status == BookingStatus.CONFIRMED.value:
        return booking_service.check_in(db, booking, current_user)
    return booking_service.mark_completed(db, booking)


@router.put("/staff/{booking_id}/reschedule", response_model=BookingResponse)
def reschedule_booking_at_counter(
    booking_id: int,
    payload: RescheduleRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(venue_staff),
):
    """Dời đơn sang sân/ngày/giờ khác trong cùng cụm sân theo yêu cầu của khách."""
    booking = _get_staff_booking(db, booking_id, current_user)
    if not booking.details:
        raise HTTPException(status_code=400, detail="Đơn đặt không có khung giờ nào")
    first = booking.details[0]
    return booking_service.reschedule(
        db,
        booking,
        current_user,
        court_id=payload.court_id or first.court_id,
        new_date=payload.booking_date or first.date,
        new_start=payload.start_time or first.start_time,
    )


@router.get("/owner/list", response_model=List[BookingResponse])
def get_owner_bookings(db: Session = Depends(deps.get_db), current_user: User = Depends(venue_staff)):
    """Toàn bộ đơn thuộc các cụm sân người dùng quản lý hoặc được phân công."""
    return booking_service.list_venue_bookings(db, managed_venue_ids(db, current_user))


def _count_bookings(db: Session, venue_ids: Optional[List[int]], *filters) -> int:
    booking_ids = ledger.venue_booking_ids_subquery(db, venue_ids)
    return db.query(Booking.id).filter(Booking.id.in_(db.query(booking_ids.c.booking_id)), *filters).count()


def _daily_series(revenue: Dict[date, float], created: Dict[date, int]) -> List[dict]:
    return [
        {"date": d.isoformat(), "revenue": revenue.get(d, 0.0), "bookings": created.get(d, 0)}
        for d in sorted(set(revenue) | set(created))
    ]


def _daily_activity(db: Session, venue_ids: Optional[List[int]]) -> List[dict]:
    """Thực thu và số đơn được tạo theo từng ngày (giờ Việt Nam), cũ trước mới sau. Ngày không phát sinh gì thì không có dòng."""
    revenue = ledger.daily_net_revenue(db, venue_ids=venue_ids)
    booking_ids = ledger.venue_booking_ids_subquery(db, venue_ids)
    day = ledger.vn_day(Booking.created_at)
    created = dict(
        db.query(day, func.count(Booking.id))
        .filter(Booking.created_at.isnot(None), Booking.id.in_(db.query(booking_ids.c.booking_id)))
        .group_by(day)
        .all()
    )
    return _daily_series(revenue, created)


def _daily_activity_by_venue(db: Session, venue_ids: List[int]) -> List[List[dict]]:
    """Như _daily_activity nhưng tách theo cụm sân của đơn: mỗi cụm sân một chuỗi, cùng thứ tự với venue_ids.

    Cộng các cụm sân lại ra đúng chuỗi tổng, vì mỗi đơn chỉ thuộc một cụm sân.
    """
    revenue = ledger.daily_net_revenue_by_venue(db, venue_ids=venue_ids)
    booking_venue = ledger.booking_venue_subquery(db)
    day = ledger.vn_day(Booking.created_at)
    rows = (
        db.query(booking_venue.c.venue_id, day, func.count(Booking.id))
        .select_from(Booking)
        .join(booking_venue, booking_venue.c.booking_id == Booking.id)
        .filter(Booking.created_at.isnot(None), booking_venue.c.venue_id.in_(venue_ids or [0]))
        .group_by(booking_venue.c.venue_id, day)
        .all()
    )
    created: Dict[int, Dict[date, int]] = {}
    for venue_id, day_value, count in rows:
        created.setdefault(venue_id, {})[day_value] = int(count)
    return [_daily_series(revenue.get(venue_id, {}), created.get(venue_id, {})) for venue_id in venue_ids]


@router.get("/owner/stats")
def get_owner_stats(db: Session = Depends(deps.get_db), current_user: User = Depends(venue_staff)):
    """Thống kê của các cụm sân đang quản lý. Doanh thu lấy từ sổ giao dịch, không ước lượng."""
    venue_ids = managed_venue_ids(db, current_user)
    venue_query = db.query(Venue)
    if venue_ids is not None:
        venue_query = venue_query.filter(Venue.id.in_(venue_ids or [0]))
    venues = venue_query.order_by(Venue.id.asc()).all()
    scope = [v.id for v in venues]

    collected = ledger.sum_transactions(db, venue_ids=scope, kinds=ledger.INCOMING_KINDS)
    refunded = ledger.sum_transactions(db, venue_ids=scope, kinds=(PaymentKind.REFUND.value,))
    return {
        "total_revenue": collected - refunded,
        "collected_amount": collected,
        "refunded_amount": refunded,
        "deposit_collected": ledger.sum_transactions(db, venue_ids=scope, kinds=(PaymentKind.DEPOSIT.value,)),
        "completed_bookings": _count_bookings(db, scope, Booking.status == BookingStatus.COMPLETED.value),
        "pending_bookings": _count_bookings(db, scope, Booking.status == BookingStatus.PENDING.value),
        "pending_refunds": _count_bookings(db, scope, Booking.refund_status == "PENDING"),
        "total_bookings": _count_bookings(db, scope),
        "total_courts": db.query(Court.id).filter(Court.venue_id.in_(scope or [0])).count(),
        "venue_names": [v.name for v in venues],
        "daily": _daily_activity(db, scope),
        "by_venue": [
            {"venue_id": v.id, "venue_name": v.name, "daily": daily}
            for v, daily in zip(venues, _daily_activity_by_venue(db, scope))
        ],
    }


@router.get("/staff/stats")
def get_staff_shift_stats(db: Session = Depends(deps.get_db), current_user: User = Depends(venue_staff)):
    """Số liệu trong ngày (giờ Việt Nam) của cụm sân mà nhân viên trực."""
    venue_ids = managed_venue_ids(db, current_user)
    venue_query = db.query(Venue)
    if venue_ids is not None:
        if not venue_ids:
            raise HTTPException(status_code=400, detail="Tài khoản nhân viên chưa được gán cụm sân trực thuộc.")
        venue_query = venue_query.filter(Venue.id.in_(venue_ids))
    venue = venue_query.order_by(Venue.id.asc()).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Không tìm thấy cụm sân")

    today = today_vn()
    since, until = vn_day_bounds_utc(today)
    scope = [venue.id]

    def collected(**kwargs) -> float:
        return ledger.sum_transactions(db, venue_ids=scope, since=since, until=until, **kwargs)

    def bookings_today(*statuses: str) -> int:
        return (
            db.query(Booking.id)
            .join(BookingDetail, BookingDetail.booking_id == Booking.id)
            .join(Court, Court.id == BookingDetail.court_id)
            .filter(Court.venue_id == venue.id, BookingDetail.date == today, Booking.status.in_(statuses))
            .distinct()
            .count()
        )

    profile = current_user.staff_profile
    checked_in = bookings_today(BookingStatus.CHECKED_IN.value, BookingStatus.COMPLETED.value)
    waiting = bookings_today(BookingStatus.CONFIRMED.value)
    return {
        "venue_id": venue.id,
        "venue_name": venue.name,
        "venue_address": venue.address,
        "staff_name": profile.full_name if profile and profile.full_name else current_user.email.split("@")[0],
        "today_date": today.strftime("%Y-%m-%d"),
        "today_revenue": collected(kinds=ledger.INCOMING_KINDS),
        "today_deposit_online": collected(kinds=(PaymentKind.DEPOSIT.value,), method=PaymentMethod.BANK_TRANSFER.value),
        "today_cash_collected": collected(kinds=ledger.INCOMING_KINDS, method=PaymentMethod.CASH.value),
        # Mọi khoản nhận bằng chuyển khoản (cọc qua VietQR và khoản khách chuyển tại quầy): tiền mặt + chuyển khoản = tổng thu
        "today_transfer_collected": collected(kinds=ledger.INCOMING_KINDS, method=PaymentMethod.BANK_TRANSFER.value),
        "today_total_bookings": checked_in + waiting,
        "today_completed_bookings": checked_in,
        "today_pending_bookings": waiting,
        "today_courts_count": len(venue.courts),
    }


# ==========================================
# ADMIN
# ==========================================

@router.get("", response_model=List[BookingResponse])
@router.get("/admin/all", response_model=List[BookingResponse])
def get_all_bookings_admin(db: Session = Depends(deps.get_db), _: User = Depends(admin_only)):
    return booking_service.list_venue_bookings(db, None)


@router.delete("/admin/{booking_id}")
def admin_delete_booking(booking_id: int, db: Session = Depends(deps.get_db), _: User = Depends(admin_only)):
    """
    Dữ liệu đặt sân không bị xóa vật lý để giữ thống kê và truy vết. Chỉ xóa được đơn rác:
    đã hủy/hết hạn và chưa từng phát sinh giao dịch.
    """
    booking = booking_service.get_booking_or_404(db, booking_id)
    has_transactions = db.query(PaymentTransaction.id).filter(PaymentTransaction.booking_id == booking_id).first()
    if booking.status not in (BookingStatus.CANCELLED.value, BookingStatus.EXPIRED.value) or has_transactions:
        raise HTTPException(
            status_code=409,
            detail="Chỉ xóa được đơn đã hủy/hết hạn và chưa có giao dịch. Với đơn khác, hãy hủy đơn thay vì xóa.",
        )
    from app.models.match import Match

    db.query(Match).filter(Match.booking_id == booking_id).update({"booking_id": None})
    db.delete(booking)
    db.commit()
    return {"status": "success", "message": f"Đã xóa đơn đặt sân #{booking_id}"}
