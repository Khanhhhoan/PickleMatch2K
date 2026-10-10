from datetime import date, datetime, time, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.booking_policy import MAX_ADVANCE_DAYS, SLOT_MINUTES
from app.models.booking import Booking, BookingDetail, BookingStatus
from app.models.venue import Court, OperatingHour, PriceRule, Venue, VenueStatus
from app.schemas.search import CourtAvailability, TimeSlot, VenueAvailabilityResponse
from app.utils.timeutils import now_utc, now_vn, vn_datetime

DEFAULT_HOURLY_PRICE = 160000.0
DEFAULT_PEAK_START = time(17, 0)
DEFAULT_PEAK_END = time(23, 0)


def calculate_slot_price(
    slot_start: time,
    slot_end: time,
    rules: List[PriceRule],
    target_date: Optional[date] = None,
    court: Optional[Court] = None,
) -> float:
    """
    Giá của MỘT khung giờ 60 phút bắt đầu lúc slot_start (đơn nhiều giờ = tổng giá từng khung):
    1. Giá cơ sở: giá riêng của sân nếu có, ngược lại giá BASE của cụm sân.
    2. Khung bắt đầu trong giờ cao điểm (mặc định 17:00-23:00) áp dụng giá PEAK.
    3. Thứ 7 và Chủ nhật áp dụng giá WEEKEND; trong giờ cao điểm lấy mức cao hơn giữa PEAK và WEEKEND.
    """
    peak_rule = next((r for r in rules if r.rule_type in ("PEAK", "PEAK_HOUR")), None)
    weekend_rule = next((r for r in rules if r.rule_type == "WEEKEND"), None)
    base_rule = next((r for r in rules if r.rule_type == "BASE"), None)

    court_price = getattr(court, "price", None) if court is not None else None
    if court_price and court_price > 0:
        base_price = float(court_price)
    elif base_rule:
        base_price = float(base_rule.price)
    elif rules:
        base_price = float(rules[0].price)
    else:
        base_price = DEFAULT_HOURLY_PRICE

    peak_price = max(base_price, float(peak_rule.price)) if peak_rule else base_price
    p_start = peak_rule.start_time if peak_rule and peak_rule.start_time else DEFAULT_PEAK_START
    p_end = peak_rule.end_time if peak_rule and peak_rule.end_time else DEFAULT_PEAK_END

    is_peak_slot = p_start <= slot_start < p_end
    is_weekend = target_date is not None and target_date.weekday() in (5, 6)

    if is_weekend and weekend_rule and weekend_rule.price:
        weekend_price = max(base_price, float(weekend_rule.price))
        return max(peak_price, weekend_price) if is_peak_slot else weekend_price
    return peak_price if is_peak_slot else base_price


def get_operating_hour(venue: Venue, target_date: date) -> Optional[OperatingHour]:
    """Giờ hoạt động của cụm sân trong ngày; None nếu ngày đó sân nghỉ."""
    weekday = target_date.weekday()
    return next((oh for oh in venue.operating_hours if oh.day_of_week == weekday), None)


def iter_day_slots(open_time: time, close_time: time) -> List[Tuple[time, time]]:
    """Lưới khung giờ 60 phút tính từ giờ mở cửa; phần lẻ cuối ngày không đủ 60 phút bị bỏ."""
    slots = []
    cursor = datetime.combine(date.min, open_time)
    end = datetime.combine(date.min, close_time)
    step = timedelta(minutes=SLOT_MINUTES)
    while cursor + step <= end:
        slots.append((cursor.time(), (cursor + step).time()))
        cursor += step
    return slots


def is_valid_slot(venue: Venue, target_date: date, start: time, end: time) -> bool:
    """Khung giờ phải nằm đúng trên lưới 60 phút trong giờ hoạt động của ngày đó."""
    operating_hour = get_operating_hour(venue, target_date)
    if operating_hour is None:
        return False
    return (start, end) in iter_day_slots(operating_hour.open_time, operating_hour.close_time)


def active_booking_filter(now: Optional[datetime] = None):
    """Điều kiện SQL: dòng chi tiết còn chiếm slot (đơn còn hiệu lực và chưa quá hạn thanh toán cọc)."""
    now = now or now_utc()
    return and_(
        BookingDetail.is_active.is_(True),
        or_(
            Booking.status != BookingStatus.PENDING.value,
            Booking.expires_at.is_(None),
            Booking.expires_at > now,
        ),
    )


def get_venue_availability(
    db: Session, venue_id: int, target_date: date, viewer_id: Optional[int] = None
) -> Optional[VenueAvailabilityResponse]:
    """Lịch trống theo từng sân của một ngày. Hàm chỉ đọc dữ liệu, không thay đổi trạng thái đơn."""
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        return None

    courts_avail: List[CourtAvailability] = []
    operating_hour = get_operating_hour(venue, target_date)
    if operating_hour and venue.status == VenueStatus.ACTIVE.value:
        now_local = now_vn()
        too_far = target_date > now_local.date() + timedelta(days=MAX_ADVANCE_DAYS)

        booked = (
            db.query(BookingDetail.court_id, BookingDetail.start_time, BookingDetail.end_time)
            .join(Booking, Booking.id == BookingDetail.booking_id)
            .join(Court, Court.id == BookingDetail.court_id)
            .filter(Court.venue_id == venue_id, BookingDetail.date == target_date, active_booking_filter())
            .all()
        )
        booked_by_court = {}
        for court_id, start, end in booked:
            booked_by_court.setdefault(court_id, []).append((start, end))

        from app.services.slot_lock_service import slot_lock_manager

        holds = {
            (h["court_id"], h["start_time"][:5]): h
            for h in slot_lock_manager.get_holds_for_venue(venue_id, str(target_date))
        }

        day_slots = iter_day_slots(operating_hour.open_time, operating_hour.close_time)
        for court in venue.courts:
            if court.status != "ACTIVE":
                continue
            court_slots = []
            for slot_start, slot_end in day_slots:
                is_past = vn_datetime(target_date, slot_start) <= now_local
                is_booked = any(slot_start < b_end and b_start < slot_end for b_start, b_end in booked_by_court.get(court.id, []))
                hold = holds.get((court.id, slot_start.strftime("%H:%M")))
                held_by_me = bool(hold and viewer_id is not None and hold["user_id"] == viewer_id)
                free = not (is_past or is_booked or too_far)
                court_slots.append(TimeSlot(
                    start_time=slot_start,
                    end_time=slot_end,
                    price=calculate_slot_price(slot_start, slot_end, venue.price_rules, target_date=target_date, court=court),
                    is_available=free,
                    is_past=is_past,
                    is_held=bool(hold and free and not held_by_me),
                    held_by_me=bool(held_by_me and free),
                    hold_seconds_remaining=hold["seconds_remaining"] if hold and free else None,
                ))
            courts_avail.append(CourtAvailability(court_id=court.id, court_name=court.name, slots=court_slots))

    return VenueAvailabilityResponse(venue_id=venue.id, date=target_date, courts=courts_avail)
