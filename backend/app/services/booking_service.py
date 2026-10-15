"""
Nghiệp vụ đặt sân.

Vòng đời một đơn:
    PENDING ──(nhận đủ cọc)──> CONFIRMED ──(check-in)──> CHECKED_IN ──(hết giờ)──> COMPLETED
       │                           │  └─(hết giờ, không đến)──> NO_SHOW
       ├─(quá 15 phút)──> EXPIRED  └─(hủy)──> CANCELLED
       └─(hủy)──> CANCELLED
Đơn tạo tại quầy (source = DESK) bắt đầu ở CONFIRMED hoặc CHECKED_IN. Đơn tại quầy chưa thu đồng nào tự hủy khi
còn `Venue.unpaid_desk_release_minutes` phút nữa tới giờ chơi (xem release_unpaid_desk_bookings).

Bảo đảm không đặt trùng: mỗi dòng BookingDetail là một khung 60 phút; CSDL có unique index
(court_id, date, start_time) và ràng buộc loại trừ khoảng thời gian trên các dòng is_active.
Mọi thay đổi trạng thái đều đi qua các hàm trong module này.
"""
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core import booking_policy as policy
from app.core.money import split_evenly, vnd
from app.core.websocket_manager import dispatch, manager
from app.models.booking import Booking, BookingDetail, BookingSource, BookingStatus, PaymentStatus, RefundStatus
from app.models.match import Match, MatchStatus
from app.models.payment import PaymentKind, PaymentMethod
from app.models.user import User
from app.models.venue import Court, VenueStatus
from app.services import ledger
from app.services.availability_service import active_booking_filter, calculate_slot_price, is_valid_slot
from app.services.code_generator import generate_next_booking_code
from app.services.slot_lock_service import slot_lock_manager
from app.utils.timeutils import as_utc, now_utc, now_vn, today_vn, vn_datetime

logger = logging.getLogger("pickleball.booking")

S = BookingStatus


@dataclass(frozen=True)
class SlotRequest:
    court_id: int
    date: date
    start_time: time
    end_time: time


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def split_into_hourly_slots(court_id: int, day: date, start: time, end: time) -> List[SlotRequest]:
    """Tách một khoảng thời gian liên tục (đơn tại quầy) thành các khung 60 phút."""
    start_dt, end_dt = datetime.combine(day, start), datetime.combine(day, end)
    minutes = (end_dt - start_dt).total_seconds() / 60
    if minutes <= 0 or minutes % policy.SLOT_MINUTES != 0:
        raise _error(400, f"Thời lượng đặt sân phải là bội số của {policy.SLOT_MINUTES} phút và giờ kết thúc sau giờ bắt đầu.")
    step = timedelta(minutes=policy.SLOT_MINUTES)
    slots, cursor = [], start_dt
    while cursor < end_dt:
        slots.append(SlotRequest(court_id, day, cursor.time(), (cursor + step).time()))
        cursor += step
    return slots


def first_slot_start(booking: Booking) -> datetime:
    return min(vn_datetime(d.date, d.start_time) for d in booking.details)


def last_slot_end(booking: Booking) -> datetime:
    return max(vn_datetime(d.date, d.end_time) for d in booking.details)


def recalculate_payment_status(booking: Booking) -> None:
    paid, total, deposit = vnd(booking.paid_amount), vnd(booking.total_price), vnd(booking.deposit_amount)
    if paid > 0:
        booking.auto_release_at = None  # đã thu tiền thì đơn tại quầy không còn tự hủy
    if paid >= total - policy.PAYMENT_TOLERANCE and total > 0:
        booking.payment_status = PaymentStatus.FULLY_PAID.value
    elif paid >= deposit - policy.PAYMENT_TOLERANCE and paid > 0:
        booking.payment_status = PaymentStatus.DEPOSIT_PAID.value
    elif paid > 0:
        booking.payment_status = PaymentStatus.PARTIALLY_PAID.value
    else:
        booking.payment_status = PaymentStatus.UNPAID.value


def _desk_release_deadline(booking: Booking, venue) -> Optional[datetime]:
    """
    Hạn tự hủy của một đơn tại quầy chưa thu đồng nào: giờ chơi trừ `unpaid_desk_release_minutes` của cụm sân.
    None nếu cụm sân tắt tính năng (0 phút), đơn đã có tiền, hoặc hạn đã qua lúc tạo/dời đơn (nhân viên chủ động giữ
    chỗ sát giờ cho khách đang tới thì không tự hủy).
    """
    minutes = getattr(venue, "unpaid_desk_release_minutes", 0) or 0
    if not minutes or vnd(booking.paid_amount) > 0 or not booking.details:
        return None
    deadline = first_slot_start(booking) - timedelta(minutes=minutes)
    return deadline if deadline > now_vn() else None


def _set_slots_active(booking: Booking, active: bool) -> None:
    for detail in booking.details:
        detail.is_active = active


def _cancel_linked_matches(db: Session, booking: Booking) -> None:
    """Đơn không còn hiệu lực thì phòng đấu gắn với đơn cũng bị hủy."""
    matches = db.query(Match).filter(
        Match.booking_id == booking.id,
        Match.status.in_([MatchStatus.OPEN.value, MatchStatus.FULL.value]),
    ).all()
    for match in matches:
        match.status = MatchStatus.CANCELLED.value
        dispatch(manager.broadcast_global({
            "type": "MATCH_UPDATED",
            "match_id": match.id,
            "status": match.status,
            "message": f"Phòng đấu #{match.id} đã bị hủy do lịch đặt sân không còn hiệu lực.",
        }))


def _slot_payload(detail: BookingDetail, available: bool) -> dict:
    return {
        "court_id": detail.court_id,
        "court_name": detail.court_name,
        "date": str(detail.date),
        "start_time": str(detail.start_time),
        "end_time": str(detail.end_time),
        "is_available": available,
    }


def _broadcast_slots(booking: Booking, event_type: str, message: str, available: bool) -> None:
    venue_id = booking.venue_id
    if not venue_id or not booking.details:
        return
    dispatch(manager.broadcast_venue_event(venue_id, {
        "type": event_type,
        "venue_id": venue_id,
        "booking_id": booking.id,
        "date": str(booking.details[0].date),
        "slots": [_slot_payload(d, available) for d in booking.details],
        "message": message,
    }))


def _broadcast_status(booking: Booking, message: str) -> None:
    dispatch(manager.broadcast_global({
        "type": "BOOKING_STATUS_CHANGED",
        "booking_id": booking.id,
        "venue_id": booking.venue_id,
        "status": booking.status,
        "payment_status": booking.payment_status,
        "refund_status": booking.refund_status,
        "message": message,
    }))


def booking_query(db: Session):
    return db.query(Booking).options(
        joinedload(Booking.user).joinedload(User.player_profile),
        joinedload(Booking.user).joinedload(User.owner_profile),
        joinedload(Booking.details).joinedload(BookingDetail.court).joinedload(Court.venue),
    )


def get_booking_or_404(db: Session, booking_id: int, *, for_update: bool = False) -> Booking:
    query = db.query(Booking).filter(Booking.id == booking_id)
    if for_update:
        # populate_existing: đọc lại dữ liệu mới nhất sau khi giành được khóa dòng
        query = query.populate_existing().with_for_update()
    booking = query.first()
    if not booking:
        raise _error(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn đặt sân")
    return booking


# ---------------------------------------------------------------------------
# Expiry of unpaid bookings
# ---------------------------------------------------------------------------
def _expire(db: Session, booking: Booking) -> None:
    """PENDING -> EXPIRED: trả slot; nếu khách đã chuyển một phần thì tạo yêu cầu hoàn."""
    booking.status = S.EXPIRED.value
    booking.expires_at = None
    _set_slots_active(booking, False)
    if (booking.paid_amount or 0) > 0:
        booking.refund_status = RefundStatus.PENDING.value
        booking.refund_amount = booking.paid_amount
        booking.refund_reason = "Đơn hết hạn khi chưa chuyển đủ tiền cọc"
    _cancel_linked_matches(db, booking)


def expire_stale_pending(db: Session, *, user_id: Optional[int] = None) -> List[int]:
    """Hết hạn các đơn PENDING quá hạn thanh toán cọc. Trả về id các đơn vừa hết hạn."""
    query = db.query(Booking).filter(Booking.status == S.PENDING.value, Booking.expires_at <= now_utc())
    if user_id is not None:
        query = query.filter(Booking.user_id == user_id)
    stale = query.with_for_update(skip_locked=True).all()
    for booking in stale:
        _expire(db, booking)
    if stale:
        db.commit()
        for booking in stale:
            _broadcast_slots(booking, "SLOT_RELEASED", "Một khung giờ vừa được mở lại do đơn hết hạn giữ chỗ.", True)
            _broadcast_status(booking, f"Đơn {booking.booking_code} đã hết hạn thanh toán cọc.")
    return [b.id for b in stale]


def _expire_stale_pending_on_slots(db: Session, slots: Sequence[SlotRequest]) -> None:
    """
    Trước khi ghi đơn mới: trả lại các slot đang bị đơn PENDING quá hạn chiếm (không chờ tác vụ nền).
    Đơn đang bị giao dịch khác khóa (ví dụ tiền cọc đến muộn đang được ghi nhận) thì bỏ qua: nếu đơn đó được
    xác nhận, slot vẫn thuộc về nó và ràng buộc CSDL sẽ từ chối đơn mới.
    """
    court_ids = {s.court_id for s in slots}
    dates = {s.date for s in slots}
    stale = (
        db.query(Booking)
        .join(BookingDetail, BookingDetail.booking_id == Booking.id)
        .filter(
            Booking.status == S.PENDING.value,
            Booking.expires_at <= now_utc(),
            BookingDetail.is_active.is_(True),
            BookingDetail.court_id.in_(court_ids),
            BookingDetail.date.in_(dates),
        )
        .populate_existing()
        .with_for_update(of=Booking, skip_locked=True)
        .all()
    )
    for booking in {b.id: b for b in stale}.values():
        _expire(db, booking)
    if stale:
        db.flush()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
def create_booking(
    db: Session,
    *,
    user: User,
    slots: Sequence[SlotRequest],
    source: str = BookingSource.ONLINE.value,
    guest_name: Optional[str] = None,
    guest_phone: Optional[str] = None,
    desk_paid: str = "NONE",  # FULL | DEPOSIT | NONE (chỉ áp dụng cho đơn tại quầy)
    desk_method: str = PaymentMethod.CASH.value,
    price_override: Optional[float] = None,
    check_in_now: bool = False,
) -> Booking:
    is_desk = source == BookingSource.DESK.value
    slots = sorted(set(slots), key=lambda s: (s.date, s.court_id, s.start_time))
    if not slots:
        raise _error(400, "Vui lòng chọn ít nhất một khung giờ.")
    if len(slots) > policy.MAX_SLOTS_PER_BOOKING:
        raise _error(400, f"Mỗi đơn chỉ được đặt tối đa {policy.MAX_SLOTS_PER_BOOKING} khung giờ.")

    now_local = now_vn()
    if not is_desk:
        pending = db.query(Booking).filter(
            Booking.user_id == user.id,
            Booking.source == BookingSource.ONLINE.value,
            Booking.status == S.PENDING.value,
            Booking.expires_at > now_utc(),
        ).count()
        if pending >= policy.MAX_PENDING_BOOKINGS_PER_USER:
            raise _error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Bạn đang có {pending} đơn chờ thanh toán cọc. Hãy thanh toán hoặc hủy bớt trước khi đặt thêm.",
            )

    # Khóa các sân theo thứ tự id để tránh deadlock khi nhiều người đặt cùng lúc
    courts = {}
    for court_id in sorted({s.court_id for s in slots}):
        court = db.query(Court).filter(Court.id == court_id).with_for_update().first()
        if not court or court.status != "ACTIVE":
            raise _error(400, "Sân không tồn tại hoặc đang tạm ngưng nhận đặt.")
        courts[court_id] = court

    venue_ids = {c.venue_id for c in courts.values()}
    if len(venue_ids) != 1:
        raise _error(400, "Một đơn chỉ được đặt các sân thuộc cùng một cụm sân.")
    venue = next(iter(courts.values())).venue
    if venue.status != VenueStatus.ACTIVE.value:
        raise _error(400, "Cụm sân hiện không nhận đặt lịch.")

    for slot in slots:
        if not is_valid_slot(venue, slot.date, slot.start_time, slot.end_time):
            raise _error(400, f"Khung giờ {slot.start_time:%H:%M}-{slot.end_time:%H:%M} ngày {slot.date} không nằm trong giờ hoạt động của sân.")
        if slot.date > now_local.date() + timedelta(days=policy.MAX_ADVANCE_DAYS):
            raise _error(400, f"Chỉ có thể đặt sân trước tối đa {policy.MAX_ADVANCE_DAYS} ngày.")
        # Khách online phải đặt trước giờ bắt đầu; khách tại quầy có thể vào sân khi khung giờ đang diễn ra
        deadline = vn_datetime(slot.date, slot.end_time if is_desk else slot.start_time)
        if deadline <= now_local:
            raise _error(400, f"Khung giờ {slot.start_time:%H:%M} ngày {slot.date} đã qua, không thể đặt.")

    _expire_stale_pending_on_slots(db, slots)

    for slot in slots:
        taken = (
            db.query(BookingDetail.id)
            .join(Booking, Booking.id == BookingDetail.booking_id)
            .filter(
                BookingDetail.court_id == slot.court_id,
                BookingDetail.date == slot.date,
                BookingDetail.start_time < slot.end_time,
                BookingDetail.end_time > slot.start_time,
                active_booking_filter(),
            )
            .first()
        )
        if taken:
            db.rollback()
            raise _error(status.HTTP_409_CONFLICT, f"Khung giờ {slot.start_time:%H:%M} tại {courts[slot.court_id].name} đã có người đặt.")
        if slot_lock_manager.is_slot_held_by_other(slot.court_id, str(slot.date), str(slot.start_time), user.id):
            db.rollback()
            raise _error(status.HTTP_409_CONFLICT, f"Khung giờ {slot.start_time:%H:%M} tại {courts[slot.court_id].name} đang được người khác tạm giữ.")

    prices = [
        calculate_slot_price(s.start_time, s.end_time, venue.price_rules, target_date=s.date, court=courts[s.court_id])
        for s in slots
    ]
    if is_desk and price_override is not None and price_override > 0:
        # Nhân viên nhập tổng tiền thỏa thuận: chia đều cho các khung giờ
        prices = split_evenly(vnd(price_override), len(slots))
    prices = [vnd(price) for price in prices]
    total = sum(prices)

    booking = Booking(
        user_id=user.id,
        booking_code=generate_next_booking_code(db),
        source=source,
        guest_name=(guest_name or None) if is_desk else None,
        guest_phone=(guest_phone or None) if is_desk else None,
        total_price=total,
        deposit_amount=policy.deposit_for(total),
        paid_amount=0,
        status=S.PENDING.value,
        payment_status=PaymentStatus.UNPAID.value,
        expires_at=now_utc() + policy.PENDING_PAYMENT_TTL,
    )
    for slot, price in zip(slots, prices):
        booking.details.append(BookingDetail(
            court_id=slot.court_id, date=slot.date, start_time=slot.start_time, end_time=slot.end_time,
            price=price, is_active=True,
        ))
    db.add(booking)
    try:
        db.flush()
    except IntegrityError:
        # Ràng buộc CSDL chặn trường hợp hai giao dịch cùng ghi một slot
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "Khung giờ vừa được người khác đặt. Vui lòng chọn khung giờ khác.")

    if is_desk:
        booking.status = S.CHECKED_IN.value if check_in_now else S.CONFIRMED.value
        booking.expires_at = None
        amount = total if desk_paid == "FULL" else booking.deposit_amount if desk_paid == "DEPOSIT" else 0
        if amount > 0:
            ledger.record_transaction(
                db, booking, amount=amount, kind=PaymentKind.DEPOSIT.value, method=desk_method,
                gateway="Tại quầy", content=f"Thu tại quầy {booking.booking_code}", created_by_id=user.id,
            )
            booking.paid_amount = amount
        recalculate_payment_status(booking)
        if check_in_now:
            booking.checked_in_at = now_utc()
            booking.checked_in_by_id = user.id
        else:
            booking.auto_release_at = _desk_release_deadline(booking, venue)

    db.commit()
    db.refresh(booking)

    for slot in slots:
        slot_lock_manager.release_after_booking(slot.court_id, str(slot.date), str(slot.start_time))
    _broadcast_slots(booking, "SLOT_BOOKED", f"Vừa có lượt đặt sân tại {venue.name}.", False)
    _broadcast_status(booking, f"Đơn {booking.booking_code} vừa được tạo.")
    return booking


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_my_bookings(db: Session, user_id: int) -> List[Booking]:
    expire_stale_pending(db, user_id=user_id)
    return (
        booking_query(db)
        .filter(Booking.user_id == user_id, Booking.source == BookingSource.ONLINE.value)
        .order_by(Booking.id.desc())
        .all()
    )


def list_venue_bookings(db: Session, venue_ids: Optional[List[int]]) -> List[Booking]:
    """Đơn đặt của các cụm sân cho trước (None = toàn hệ thống), mới nhất trước."""
    query = booking_query(db)
    if venue_ids is not None:
        if not venue_ids:
            return []
        booking_ids = ledger.venue_booking_ids_subquery(db, venue_ids)
        query = query.filter(Booking.id.in_(db.query(booking_ids.c.booking_id)))
    return query.order_by(Booking.created_at.desc(), Booking.id.desc()).all()


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
def _slots_still_free(db: Session, booking: Booking) -> bool:
    now_local = now_vn()
    for detail in booking.details:
        if vn_datetime(detail.date, detail.start_time) <= now_local:
            return False
        taken = (
            db.query(BookingDetail.id)
            .join(Booking, Booking.id == BookingDetail.booking_id)
            .filter(
                BookingDetail.booking_id != booking.id,
                BookingDetail.court_id == detail.court_id,
                BookingDetail.date == detail.date,
                BookingDetail.start_time < detail.end_time,
                BookingDetail.end_time > detail.start_time,
                active_booking_filter(),
            )
            .first()
        )
        if taken:
            return False
    return True


def _request_refund(booking: Booking, amount: int, reason: str) -> None:
    booking.refund_status = RefundStatus.PENDING.value
    booking.refund_amount = vnd(amount)
    booking.refund_reason = reason


def apply_payment(db: Session, booking: Booking, amount: int) -> str:
    """
    Cập nhật đơn sau khi một khoản tiền vào đã được ghi sổ. Không commit (người gọi commit).
    Trả về: confirmed | partial | updated | reactivated | late_refund | recorded.
    """
    booking.paid_amount = vnd(booking.paid_amount) + vnd(amount)
    recalculate_payment_status(booking)
    deposit_met = booking.paid_amount >= vnd(booking.deposit_amount) - policy.PAYMENT_TOLERANCE

    if booking.status == S.PENDING.value:
        if deposit_met:
            booking.status = S.CONFIRMED.value
            booking.expires_at = None
            return "confirmed"
        return "partial"

    if booking.status == S.EXPIRED.value:
        # Tiền đến sau khi đơn hết hạn: chỉ khôi phục nếu đủ cọc và slot vẫn còn trống
        if deposit_met and _slots_still_free(db, booking):
            try:
                with db.begin_nested():
                    _set_slots_active(booking, True)
                    db.flush()
                booking.status = S.CONFIRMED.value
                booking.refund_status, booking.refund_amount, booking.refund_reason = None, 0, None
                return "reactivated"
            except IntegrityError:
                _set_slots_active(booking, False)
        _request_refund(booking, booking.paid_amount, "Thanh toán đến sau khi đơn hết hạn và khung giờ đã có người khác đặt")
        return "late_refund"

    if booking.status == S.CANCELLED.value:
        already = vnd(booking.refund_amount) if booking.refund_status == RefundStatus.PENDING.value else 0
        _request_refund(booking, already + vnd(amount), booking.refund_reason or "Thanh toán đến sau khi đơn đã bị hủy")
        return "late_refund"

    if booking.status in (S.CONFIRMED.value, S.CHECKED_IN.value):
        return "updated"
    return "recorded"


def collect_payment(
    db: Session, booking: Booking, actor: User, amount: int, method: str = PaymentMethod.CASH.value
) -> Booking:
    """Nhân viên ghi nhận một khoản thu tại quầy (thu cọc cho đơn chờ, hoặc thu phần còn lại)."""
    if booking.status in (S.CANCELLED.value, S.EXPIRED.value):
        raise _error(400, "Đơn đã hủy hoặc hết hạn, không thể thu tiền.")
    remaining = booking.remaining_amount
    amount = vnd(amount)
    if amount <= 0 or amount > remaining + policy.PAYMENT_TOLERANCE:
        raise _error(400, f"Số tiền thu phải lớn hơn 0 và không vượt quá số còn lại ({remaining:,.0f}đ).")

    kind = PaymentKind.DEPOSIT.value if booking.status == S.PENDING.value else PaymentKind.BALANCE.value
    ledger.record_transaction(
        db, booking, amount=amount, kind=kind, method=method, gateway="Tại quầy",
        content=f"Thu tại quầy {booking.booking_code}", created_by_id=actor.id,
    )
    apply_payment(db, booking, amount)
    db.commit()
    db.refresh(booking)
    _broadcast_status(booking, f"Đơn {booking.booking_code} vừa được ghi nhận thanh toán tại quầy.")
    return booking


# ---------------------------------------------------------------------------
# Cancellation & refund
# ---------------------------------------------------------------------------
def preview_cancellation(booking: Booking) -> dict:
    """Số tiền người chơi được hoàn nếu hủy ngay lúc này, theo chính sách đã công bố."""
    paid, deposit = vnd(booking.paid_amount), vnd(booking.deposit_amount)
    base = {
        "booking_id": booking.id,
        "paid_amount": paid,
        "full_refund_hours": policy.CANCEL_FULL_REFUND_HOURS,
        "reschedule_hours": policy.CANCEL_RESCHEDULE_HOURS,
    }
    if booking.status not in (S.PENDING.value, S.CONFIRMED.value) or not booking.details:
        return {**base, "can_cancel": False, "tier": "NOT_ALLOWED", "hours_before": 0.0, "refund_amount": 0,
                "message": "Đơn ở trạng thái này không thể hủy."}

    hours_before = (first_slot_start(booking) - now_vn()).total_seconds() / 3600
    if booking.status == S.PENDING.value:
        tier, refund = "UNPAID", paid
        message = "Đơn chưa hoàn tất cọc: hủy sẽ trả lại khung giờ ngay."
    elif hours_before >= policy.CANCEL_FULL_REFUND_HOURS:
        tier, refund = "FULL_REFUND", paid
        message = f"Hủy trước giờ chơi từ {policy.CANCEL_FULL_REFUND_HOURS} tiếng: hoàn 100% số tiền đã thanh toán."
    elif hours_before >= policy.CANCEL_RESCHEDULE_HOURS:
        tier, refund = "RESCHEDULE_ONLY", max(0, paid - deposit)
        message = (f"Còn dưới {policy.CANCEL_FULL_REFUND_HOURS} tiếng: tiền cọc không được hoàn. "
                   "Bạn có thể liên hệ sân để được hỗ trợ dời lịch thay vì hủy.")
    else:
        tier, refund = "NO_REFUND", max(0, paid - deposit)
        message = f"Còn dưới {policy.CANCEL_RESCHEDULE_HOURS} tiếng trước giờ chơi: tiền cọc không được hoàn."
    return {**base, "can_cancel": True, "tier": tier, "hours_before": round(hours_before, 2),
            "refund_amount": refund, "message": message}


def _mark_cancelled(db: Session, booking: Booking, actor: Optional[User], reason: Optional[str]) -> None:
    """actor = None: hệ thống tự hủy (tác vụ nền)."""
    booking.status = S.CANCELLED.value
    booking.expires_at = None
    booking.cancelled_at = now_utc()
    booking.cancelled_by_id = actor.id if actor else None
    booking.cancel_reason = (reason or "").strip() or None
    _set_slots_active(booking, False)
    _cancel_linked_matches(db, booking)


def cancel_by_player(db: Session, booking_id: int, user: User, refund_info=None) -> Booking:
    booking = db.query(Booking).filter(
        Booking.id == booking_id, Booking.user_id == user.id, Booking.source == BookingSource.ONLINE.value
    ).with_for_update().first()
    if not booking:
        raise _error(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn đặt sân")

    preview = preview_cancellation(booking)
    if not preview["can_cancel"]:
        raise _error(400, preview["message"])

    refund = preview["refund_amount"]
    if refund > 0:
        account = (getattr(refund_info, "bank_account", None) or "").strip()
        holder = (getattr(refund_info, "account_holder", None) or "").strip()
        bank = (getattr(refund_info, "bank_name", None) or "").strip()
        if not (account and holder and bank):
            raise _error(400, "Vui lòng nhập ngân hàng, số tài khoản và tên chủ tài khoản để nhận tiền hoàn.")
        booking.refund_bank_account, booking.refund_account_holder, booking.refund_bank_name = account, holder, bank
        _request_refund(booking, refund, preview["message"])
    else:
        booking.refund_status, booking.refund_amount = None, 0.0

    _mark_cancelled(db, booking, user, getattr(refund_info, "reason", None))
    db.commit()
    db.refresh(booking)
    _broadcast_slots(booking, "SLOT_RELEASED", "Một khung giờ vừa được mở lại.", True)
    _broadcast_status(booking, f"Đơn {booking.booking_code} đã được hủy.")
    return booking


def cancel_by_venue(db: Session, booking: Booking, actor: User, reason: Optional[str] = None) -> Booking:
    """Cụm sân chủ động hủy: khách được hoàn toàn bộ số tiền đã trả."""
    if booking.status not in (S.PENDING.value, S.CONFIRMED.value, S.CHECKED_IN.value):
        raise _error(400, "Đơn ở trạng thái này không thể hủy.")
    paid = float(booking.paid_amount or 0)
    if paid > 0:
        _request_refund(booking, paid, "Cụm sân hủy lịch: hoàn toàn bộ số tiền đã thanh toán")
    _mark_cancelled(db, booking, actor, reason or "Cụm sân hủy lịch")
    db.commit()
    db.refresh(booking)
    _broadcast_slots(booking, "SLOT_RELEASED", "Một khung giờ vừa được mở lại.", True)
    _broadcast_status(booking, f"Đơn {booking.booking_code} đã bị cụm sân hủy.")
    return booking


def confirm_refund(db: Session, booking: Booking, actor: User, *, bank_reference: str, note: Optional[str] = None) -> Booking:
    """
    Xác nhận đã chuyển hoàn thủ công cho khách (hệ thống không tự chuyển tiền). Bắt buộc có mã giao dịch ngân hàng
    của lần chuyển; một mã chỉ dùng cho một đơn. Đơn phải được khóa dòng trước khi gọi (xem _get_staff_booking),
    nên hai lần xác nhận cùng lúc không thể cùng ghi khoản hoàn.
    """
    if booking.refund_status != RefundStatus.PENDING.value:
        raise _error(400, "Đơn này không ở trạng thái chờ hoàn tiền")
    reference = (bank_reference or "").strip()
    if not reference:
        raise _error(400, "Cần nhập mã giao dịch ngân hàng của lần chuyển hoàn.")
    used = db.query(Booking.booking_code).filter(Booking.refund_reference == reference, Booking.id != booking.id).first()
    if used:
        raise _error(status.HTTP_409_CONFLICT, f"Mã giao dịch {reference} đã được dùng để xác nhận hoàn tiền cho đơn {used[0]}.")

    amount = vnd(booking.refund_amount)
    if amount > 0:
        content = f"Hoàn tiền đơn {booking.booking_code} - mã GD {reference}"
        if (note or "").strip():
            content += f" - {note.strip()}"
        ledger.record_transaction(
            db, booking, amount=amount, kind=PaymentKind.REFUND.value, method=PaymentMethod.BANK_TRANSFER.value,
            gateway="Hoàn tiền thủ công", content=content, created_by_id=actor.id,
        )
    booking.refund_reference = reference
    booking.refund_status = RefundStatus.COMPLETED.value
    booking.refunded_at = now_utc()
    booking.refunded_by_id = actor.id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, f"Mã giao dịch {reference} đã được dùng để xác nhận hoàn tiền cho đơn khác.")
    db.refresh(booking)
    _broadcast_status(booking, f"Đơn {booking.booking_code} đã được hoàn tiền.")
    return booking


# ---------------------------------------------------------------------------
# Check-in, completion
# ---------------------------------------------------------------------------
def check_in(
    db: Session,
    booking: Booking,
    actor: User,
    collected_amount: Optional[int] = None,
    method: str = PaymentMethod.CASH.value,
) -> Booking:
    """Khách đến nhận sân. Mặc định thu luôn phần còn lại; truyền collected_amount=0 nếu thu sau."""
    if booking.status == S.PENDING.value:
        raise _error(400, "Đơn chưa thanh toán cọc nên chưa thể check-in. Hãy ghi nhận tiền cọc trước.")
    if booking.status != S.CONFIRMED.value:
        raise _error(400, "Chỉ đơn đã xác nhận mới có thể check-in.")
    if today_vn() not in {d.date for d in booking.details}:
        raise _error(400, "Chỉ có thể check-in trong đúng ngày đặt sân.")
    if last_slot_end(booking) <= now_vn():
        raise _error(400, "Khung giờ đặt đã kết thúc, không thể check-in.")

    remaining = booking.remaining_amount
    amount = remaining if collected_amount is None else vnd(collected_amount)
    if amount < 0 or amount > remaining + policy.PAYMENT_TOLERANCE:
        raise _error(400, f"Số tiền thu không hợp lệ (còn lại {remaining:,.0f}đ).")
    if amount > 0:
        ledger.record_transaction(
            db, booking, amount=amount, kind=PaymentKind.BALANCE.value, method=method, gateway="Tại quầy",
            content=f"Thu phần còn lại {booking.booking_code}", created_by_id=actor.id,
        )
        booking.paid_amount = vnd(booking.paid_amount) + amount
        recalculate_payment_status(booking)

    booking.status = S.CHECKED_IN.value
    booking.checked_in_at = now_utc()
    booking.checked_in_by_id = actor.id
    booking.auto_release_at = None
    db.commit()
    db.refresh(booking)
    _broadcast_status(booking, f"Đơn {booking.booking_code} đã check-in.")
    return booking


def mark_completed(db: Session, booking: Booking) -> Booking:
    """Nhân viên kết thúc sớm lượt chơi của đơn đã check-in."""
    if booking.status != S.CHECKED_IN.value:
        raise _error(400, "Chỉ đơn đã check-in mới có thể hoàn tất.")
    booking.status = S.COMPLETED.value
    db.commit()
    db.refresh(booking)
    _broadcast_status(booking, f"Đơn {booking.booking_code} đã hoàn tất.")
    return booking


def finalize_past_bookings(db: Session) -> List[int]:
    """
    Tác vụ nền: đơn đã qua giờ chơi -> COMPLETED (đã check-in) hoặc NO_SHOW (không đến).
    Khóa dòng với SKIP LOCKED: đơn đang được thao tác ở nơi khác (hoặc một lượt tác vụ nền khác đang xử lý) thì để
    lượt sau, nên một đơn không bao giờ bị kết thúc hai lần.
    """
    now_local = now_vn()
    candidates = (
        db.query(Booking)
        .options(selectinload(Booking.details))
        .filter(Booking.status.in_([S.CONFIRMED.value, S.CHECKED_IN.value]))
        .filter(Booking.details.any(BookingDetail.date <= now_local.date()))
        .with_for_update(skip_locked=True)
        .all()
    )
    changed = []
    for booking in candidates:
        if not booking.details or last_slot_end(booking) > now_local:
            continue
        if booking.status == S.CHECKED_IN.value:
            booking.status = S.COMPLETED.value
        else:
            booking.status = S.NO_SHOW.value
            _cancel_linked_matches(db, booking)
        changed.append(booking)
    if changed:
        db.commit()
        for booking in changed:
            _broadcast_status(booking, f"Đơn {booking.booking_code} đã kết thúc.")
    return [b.id for b in changed]


def release_unpaid_desk_bookings(db: Session) -> List[int]:
    """
    Tác vụ nền: tự hủy đơn tại quầy chưa thu đồng nào khi đã tới hạn (Booking.auto_release_at) mà chưa tới giờ chơi,
    để khách hẹn qua điện thoại rồi không đến không giữ sân mãi. Đơn đã thu tiền, đã check-in, đơn online và đơn tạo
    sát giờ không bị đụng. Khóa dòng SKIP LOCKED như các tác vụ nền khác.
    """
    now_local = now_vn()
    candidates = (
        db.query(Booking)
        .options(selectinload(Booking.details))
        .filter(
            Booking.source == BookingSource.DESK.value,
            Booking.status == S.CONFIRMED.value,
            func.coalesce(Booking.paid_amount, 0) <= 0,
            Booking.auto_release_at.isnot(None),
            Booking.auto_release_at <= now_utc(),
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    released = []
    for booking in candidates:
        start = first_slot_start(booking) if booking.details else now_local
        if start <= now_local:
            continue  # đã tới giờ chơi (ví dụ máy chủ tắt đúng lúc tới hạn): để kết thúc theo giờ như mọi đơn khác
        minutes = round((start - as_utc(booking.auto_release_at)).total_seconds() / 60)
        _mark_cancelled(db, booking, None, f"Tự hủy: chưa thanh toán khi còn {minutes} phút tới giờ chơi")
        booking.auto_release_at = None
        released.append(booking)
    if released:
        db.commit()
        for booking in released:
            _broadcast_slots(booking, "SLOT_RELEASED", "Một khung giờ vừa được mở lại do đơn tại quầy chưa thanh toán.", True)
            _broadcast_status(booking, f"Đơn {booking.booking_code} đã tự hủy vì chưa thanh toán.")
    return [b.id for b in released]


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------
def reschedule(db: Session, booking: Booking, actor: User, court_id: int, new_date: date, new_start: time) -> Booking:
    """Dời đơn sang sân/ngày/giờ khác với cùng số khung giờ. Giá đã thỏa thuận được giữ nguyên."""
    if booking.status not in (S.PENDING.value, S.CONFIRMED.value):
        raise _error(400, "Chỉ dời được lịch của đơn đang chờ cọc hoặc đã xác nhận.")
    if not booking.details:
        raise _error(400, "Đơn đặt không có khung giờ nào.")

    old_venue_id = booking.venue_id
    court = db.query(Court).filter(Court.id == court_id).with_for_update().first()
    if not court or court.status != "ACTIVE":
        raise _error(400, "Sân mới không tồn tại hoặc đang tạm ngưng.")
    if court.venue_id != old_venue_id:
        raise _error(400, "Chỉ có thể dời lịch trong cùng một cụm sân.")

    total_minutes = sum(
        (datetime.combine(d.date, d.end_time) - datetime.combine(d.date, d.start_time)).total_seconds() / 60
        for d in booking.details
    )
    hours = int(total_minutes // policy.SLOT_MINUTES)
    start_dt = datetime.combine(new_date, new_start)
    end_dt = start_dt + timedelta(minutes=policy.SLOT_MINUTES * hours)
    if hours < 1 or end_dt.date() != new_date:
        raise _error(400, "Khung giờ mới không hợp lệ.")
    new_slots = split_into_hourly_slots(court.id, new_date, new_start, end_dt.time())

    now_local = now_vn()
    for slot in new_slots:
        if not is_valid_slot(court.venue, slot.date, slot.start_time, slot.end_time):
            raise _error(400, "Khung giờ mới không nằm trong giờ hoạt động của sân.")
        if vn_datetime(slot.date, slot.end_time) <= now_local:
            raise _error(400, "Không thể dời lịch sang khung giờ đã qua.")

    old_slots = [_slot_payload(d, True) for d in booking.details]
    prices = split_evenly(vnd(booking.total_price), len(new_slots))

    try:
        booking.details.clear()
        db.flush()
        for slot, price in zip(new_slots, prices):
            booking.details.append(BookingDetail(
                court_id=slot.court_id, date=slot.date, start_time=slot.start_time, end_time=slot.end_time,
                price=price, is_active=True,
            ))
        db.flush()
    except IntegrityError:
        db.rollback()
        raise _error(status.HTTP_409_CONFLICT, "Khung giờ mới hoặc sân mới đã có người đặt!")

    for match in db.query(Match).filter(Match.booking_id == booking.id).all():
        match.court_id, match.date = court.id, new_date
        match.start_time, match.end_time = new_slots[0].start_time, new_slots[-1].end_time
    if booking.auto_release_at is not None:
        # Đơn tại quầy chưa thu: hạn tự hủy dời theo giờ chơi mới
        booking.auto_release_at = _desk_release_deadline(booking, court.venue)
    db.commit()
    db.refresh(booking)

    if old_venue_id:
        dispatch(manager.broadcast_venue_event(old_venue_id, {
            "type": "SLOT_RELEASED", "venue_id": old_venue_id, "date": old_slots[0]["date"], "slots": old_slots,
            "message": "Một khung giờ vừa được mở lại do đổi lịch.",
        }))
    _broadcast_slots(booking, "SLOT_BOOKED", "Một khung giờ vừa được đặt do đổi lịch.", False)
    dispatch(manager.broadcast_global({
        "type": "BOOKING_RESCHEDULED", "booking_id": booking.id, "venue_id": booking.venue_id,
        "message": f"Đơn {booking.booking_code} đã được đổi lịch.",
    }))
    return booking


def is_expired_pending(booking: Booking) -> bool:
    expires_at = as_utc(booking.expires_at)
    return booking.status == S.PENDING.value and expires_at is not None and expires_at <= now_utc()
