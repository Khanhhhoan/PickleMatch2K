"""
Nghiệp vụ cấu hình cụm sân. Các hàm nhận sẵn đối tượng Venue đã được kiểm tra quyền
ở tầng API (xem app.api.permissions), không tự kiểm tra quyền lại.
"""
from datetime import time
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.money import vnd
from app.core.websocket_manager import dispatch, manager
from app.models.venue import Court, CourtStatus, OperatingHour, PriceRule, Venue, VenueStatus
from app.utils.timeutils import now_utc, now_vn
from app.schemas.venue import CourtCreate, CourtUpdate, OperatingHourBase, PriceRuleCreate, VenueCreate

DEFAULT_PEAK_START = time(17, 0)
DEFAULT_PEAK_END = time(23, 0)
DEFAULT_BASE_START = time(6, 0)
PEAK_TYPES = ["PEAK", "PEAK_HOUR"]


def create_venue(db: Session, venue_in: VenueCreate, owner_id: int) -> Venue:
    if db.query(Venue).filter(Venue.owner_id == owner_id).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mỗi tài khoản chủ sân chỉ được quản lý 1 cụm sân duy nhất.",
        )
    # Cụm sân do chủ sân tự đăng ký phải chờ Admin duyệt rồi mới hiển thị công khai
    db_venue = Venue(**venue_in.model_dump(exclude={"status"}), owner_id=owner_id, status=VenueStatus.PENDING.value)
    db.add(db_venue)
    db.commit()
    db.refresh(db_venue)
    return db_venue


# ---------------------------------------------------------------------------
# Courts
# ---------------------------------------------------------------------------
def _get_court(db: Session, venue: Venue, court_id: int, *, for_update: bool = False) -> Court:
    query = db.query(Court).filter(Court.id == court_id, Court.venue_id == venue.id)
    if for_update:
        query = query.populate_existing().with_for_update()
    court = query.first()
    if not court:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sân trong cụm sân này")
    return court


def upcoming_bookings(db: Session, venue: Venue, court_id: Optional[int] = None) -> List[dict]:
    """
    Đơn còn hiệu lực có khung giờ chưa kết thúc trên một sân (hoặc cả cụm sân): đã xác nhận, đang chơi, hoặc đang chờ
    cọc mà chưa hết hạn. Mỗi phần tử là một đơn trên một sân, kèm khoảng giờ sớm nhất - muộn nhất của đơn trên sân đó.
    """
    from app.models.booking import Booking, BookingDetail, BookingStatus

    now_local = now_vn()
    today = now_local.date()
    query = (
        db.query(BookingDetail, Booking)
        .join(Booking, Booking.id == BookingDetail.booking_id)
        .join(Court, Court.id == BookingDetail.court_id)
        .filter(
            Court.venue_id == venue.id,
            BookingDetail.is_active.is_(True),
            Booking.status.in_([BookingStatus.PENDING.value, BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value]),
            or_(Booking.status != BookingStatus.PENDING.value, Booking.expires_at > now_utc()),
            or_(BookingDetail.date > today, and_(BookingDetail.date == today, BookingDetail.end_time > now_local.time())),
        )
        .order_by(BookingDetail.date, BookingDetail.start_time)
    )
    if court_id is not None:
        query = query.filter(BookingDetail.court_id == court_id)

    grouped: dict = {}
    for detail, booking in query.all():
        key = (booking.id, detail.court_id, detail.date)
        item = grouped.get(key)
        if item is None:
            grouped[key] = {
                "booking_id": booking.id,
                "booking_code": booking.booking_code,
                "status": booking.status,
                "customer_name": booking.user_name,
                "customer_phone": booking.user_phone,
                "court_id": detail.court_id,
                "court_name": detail.court_name,
                "date": detail.date,
                "start_time": detail.start_time,
                "end_time": detail.end_time,
            }
        else:
            item["start_time"] = min(item["start_time"], detail.start_time)
            item["end_time"] = max(item["end_time"], detail.end_time)
    return list(grouped.values())


def ensure_no_upcoming_bookings(db: Session, venue: Venue, court_id: Optional[int], target: str) -> None:
    """
    Chặn tạm ngưng (bảo trì, ngừng hoạt động) khi còn khách đã đặt: không âm thầm bỏ rơi hay hủy đơn của khách.
    Chủ sân dời các đơn đó sang sân khác hoặc hủy và hoàn tiền trước, rồi mới tạm ngưng được.
    """
    conflicts = upcoming_bookings(db, venue, court_id)
    if conflicts:
        codes = ", ".join(sorted({c["booking_code"] for c in conflicts}))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{target} còn {len({c['booking_id'] for c in conflicts})} đơn đặt sắp tới ({codes}). "
                   "Hãy dời các đơn này sang sân khác hoặc hủy và hoàn tiền cho khách trước khi tạm ngưng.",
        )


def _lock_courts(db: Session, venue: Venue) -> None:
    """Khóa mọi sân của cụm sân (theo thứ tự id như lúc đặt sân) để không có đơn mới chen vào giữa lúc kiểm tra và lúc ghi."""
    db.query(Court.id).filter(Court.venue_id == venue.id).order_by(Court.id).with_for_update().all()


def ensure_venue_can_pause(db: Session, venue: Venue) -> None:
    """Trước khi chuyển cả cụm sân khỏi ACTIVE: khóa mọi sân rồi kiểm tra đơn sắp tới."""
    _lock_courts(db, venue)
    ensure_no_upcoming_bookings(db, venue, None, "Cụm sân")


def ensure_hours_keep_bookings(db: Session, venue: Venue, changed: Dict[int, Optional[Tuple[time, time]]]) -> None:
    """
    Chặn đổi giờ hoạt động khi giờ mới không còn chứa trọn đơn đặt sắp tới của khách (ngày nghỉ hoặc ngoài giờ mở - đóng).
    `changed`: ngày trong tuần (0 = Thứ Hai) -> (giờ mở, giờ đóng) mới, None = nghỉ; ngày không có mặt thì giữ nguyên.
    """
    _lock_courts(db, venue)
    affected = []
    for item in upcoming_bookings(db, venue):
        weekday = item["date"].weekday()
        if weekday not in changed:
            continue
        window = changed[weekday]
        if window is None or item["start_time"] < window[0] or item["end_time"] > window[1]:
            affected.append(item)
    if affected:
        codes = ", ".join(sorted({c["booking_code"] for c in affected}))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Giờ mới không còn chứa {len({c['booking_id'] for c in affected})} đơn đặt sắp tới ({codes}). "
                   "Hãy dời các đơn này sang giờ khác hoặc hủy và hoàn tiền cho khách trước khi đổi giờ.",
        )


def create_court(db: Session, venue: Venue, court_in: CourtCreate) -> Court:
    data = court_in.model_dump()
    if not data.get("price"):
        data["price"] = None
    db_court = Court(**data, venue_id=venue.id)
    db.add(db_court)
    db.commit()
    db.refresh(db_court)
    return db_court


def update_court(db: Session, venue: Venue, court_id: int, court_in: CourtUpdate) -> Court:
    # Khóa dòng sân: đơn mới cũng khóa dòng này (booking_service.create_booking), nên không có đơn nào chen vào
    # giữa lúc kiểm tra đơn sắp tới và lúc đổi trạng thái sân.
    court = _get_court(db, venue, court_id, for_update=True)
    changes = court_in.model_dump(exclude_unset=True)
    if changes.get("name"):
        court.name = changes["name"].strip()
    new_status = changes.get("status")
    if new_status is not None:
        if new_status.value != CourtStatus.ACTIVE.value and court.status == CourtStatus.ACTIVE.value:
            ensure_no_upcoming_bookings(db, venue, court.id, f"Sân {court.name}")
        court.status = new_status.value
    if "price" in changes:
        court.price = changes["price"] or None
    db.commit()
    db.refresh(court)
    return court


def delete_court(db: Session, venue: Venue, court_id: int) -> None:
    from app.models.booking import BookingDetail
    from app.models.match import Match

    court = _get_court(db, venue, court_id)
    has_history = (
        db.query(BookingDetail.id).filter(BookingDetail.court_id == court.id).first() is not None
        or db.query(Match.id).filter(Match.court_id == court.id).first() is not None
    )
    if has_history:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sân đã có lịch sử đặt nên không thể xóa. Hãy chuyển sân sang trạng thái Bảo trì.",
        )
    db.delete(court)
    db.commit()


# ---------------------------------------------------------------------------
# Operating hours
# ---------------------------------------------------------------------------
def upsert_operating_hour(db: Session, venue: Venue, oh_in: OperatingHourBase) -> OperatingHour:
    ensure_hours_keep_bookings(db, venue, {oh_in.day_of_week: (oh_in.open_time, oh_in.close_time)})
    rows = (
        db.query(OperatingHour)
        .filter(OperatingHour.venue_id == venue.id, OperatingHour.day_of_week == oh_in.day_of_week)
        .order_by(OperatingHour.id.asc())
        .all()
    )
    if rows:
        row = rows[0]
        row.open_time, row.close_time = oh_in.open_time, oh_in.close_time
        for extra in rows[1:]:
            db.delete(extra)
    else:
        row = OperatingHour(venue_id=venue.id, **oh_in.model_dump())
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def replace_operating_hours(db: Session, venue: Venue, hours: List[OperatingHourBase]) -> List[OperatingHour]:
    """Thay toàn bộ lịch hoạt động trong tuần; ngày không được gửi lên là ngày nghỉ."""
    new_hours = {item.day_of_week: (item.open_time, item.close_time) for item in hours}
    ensure_hours_keep_bookings(db, venue, {day: new_hours.get(day) for day in range(7)})
    db.query(OperatingHour).filter(OperatingHour.venue_id == venue.id).delete(synchronize_session=False)
    for item in hours:
        db.add(OperatingHour(venue_id=venue.id, **item.model_dump()))
    db.commit()
    return (
        db.query(OperatingHour)
        .filter(OperatingHour.venue_id == venue.id)
        .order_by(OperatingHour.day_of_week.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------
def _single_rule(db: Session, venue_id: int, rule_types: List[str]) -> Optional[PriceRule]:
    """Lấy một rule của nhóm loại giá và xóa các dòng trùng lặp thừa."""
    rules = (
        db.query(PriceRule)
        .filter(PriceRule.venue_id == venue_id, PriceRule.rule_type.in_(rule_types))
        .order_by(PriceRule.id.asc())
        .all()
    )
    for extra in rules[1:]:
        db.delete(extra)
    return rules[0] if rules else None


def _set_rule(db: Session, venue_id: int, rule_type: str, price: float,
              start_time: Optional[time], end_time: Optional[time]) -> PriceRule:
    aliases = PEAK_TYPES if rule_type == "PEAK" else [rule_type]
    rule = _single_rule(db, venue_id, aliases)
    if rule is None:
        rule = PriceRule(venue_id=venue_id)
        db.add(rule)
    rule.rule_type = rule_type
    rule.price = vnd(price)
    rule.start_time, rule.end_time = start_time, end_time
    return rule


def upsert_price_rule(db: Session, venue: Venue, rule_in: PriceRuleCreate) -> PriceRule:
    rule_type = "PEAK" if rule_in.rule_type in PEAK_TYPES else rule_in.rule_type
    if rule_type not in ("BASE", "PEAK", "WEEKEND"):
        raise HTTPException(status_code=400, detail="Loại giá không hợp lệ (BASE, PEAK, WEEKEND).")

    start_time, end_time = rule_in.start_time, rule_in.end_time
    if rule_type == "PEAK":
        start_time, end_time = start_time or DEFAULT_PEAK_START, end_time or DEFAULT_PEAK_END
    elif rule_type == "BASE":
        start_time, end_time = start_time or DEFAULT_BASE_START, end_time or DEFAULT_PEAK_START

    rule = _set_rule(db, venue.id, rule_type, rule_in.price, start_time, end_time)
    db.commit()
    db.refresh(rule)

    dispatch(manager.broadcast_venue_event(venue.id, {
        "type": "PRICE_UPDATED",
        "venue_id": venue.id,
        "rule_type": rule_type,
        "price": rule.price,
        "message": f"Bảng giá {venue.name} vừa được cập nhật.",
    }))
    return rule


def update_venue_pricing(
    db: Session,
    venue: Venue,
    base_price: float,
    peak_price: Optional[float] = None,
    weekend_price: Optional[float] = None,
    peak_start: Optional[time] = None,
    peak_end: Optional[time] = None,
) -> dict:
    """Cập nhật đồng bộ ba mức giá BASE / PEAK / WEEKEND của cụm sân."""
    current_peak = _single_rule(db, venue.id, PEAK_TYPES)
    p_start = peak_start or (current_peak.start_time if current_peak and current_peak.start_time else DEFAULT_PEAK_START)
    p_end = peak_end or (current_peak.end_time if current_peak and current_peak.end_time else DEFAULT_PEAK_END)
    if p_start >= p_end:
        raise HTTPException(status_code=400, detail="Khung giờ cao điểm không hợp lệ.")

    base_rule = _set_rule(db, venue.id, "BASE", base_price, DEFAULT_BASE_START, p_start)
    peak_rule = _set_rule(db, venue.id, "PEAK", peak_price or base_price, p_start, p_end)
    weekend_rule = _set_rule(db, venue.id, "WEEKEND", weekend_price or base_price, None, None)
    db.commit()

    dispatch(manager.broadcast_venue_event(venue.id, {
        "type": "PRICE_UPDATED",
        "venue_id": venue.id,
        "base_price": base_rule.price,
        "peak_price": peak_rule.price,
        "weekend_price": weekend_rule.price,
        "message": f"Bảng giá {venue.name} vừa được cập nhật.",
    }))
    return {
        "venue_id": venue.id,
        "base_price": base_rule.price,
        "peak_price": peak_rule.price,
        "weekend_price": weekend_rule.price,
        "peak_start": p_start.strftime("%H:%M"),
        "peak_end": p_end.strftime("%H:%M"),
        "status": "success",
    }
