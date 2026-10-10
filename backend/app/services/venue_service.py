"""
Nghiệp vụ cấu hình cụm sân. Các hàm nhận sẵn đối tượng Venue đã được kiểm tra quyền
ở tầng API (xem app.api.permissions), không tự kiểm tra quyền lại.
"""
from datetime import time
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.websocket_manager import dispatch, manager
from app.models.venue import Court, OperatingHour, PriceRule, Venue, VenueStatus
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


def get_venues_by_owner(db: Session, owner_id: int) -> List[Venue]:
    return db.query(Venue).filter(Venue.owner_id == owner_id).order_by(Venue.id.asc()).all()


def get_venue(db: Session, venue_id: int) -> Optional[Venue]:
    return db.query(Venue).filter(Venue.id == venue_id).first()


# ---------------------------------------------------------------------------
# Courts
# ---------------------------------------------------------------------------
def _get_court(db: Session, venue: Venue, court_id: int) -> Court:
    court = db.query(Court).filter(Court.id == court_id, Court.venue_id == venue.id).first()
    if not court:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sân trong cụm sân này")
    return court


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
    court = _get_court(db, venue, court_id)
    changes = court_in.model_dump(exclude_unset=True)
    if changes.get("name"):
        court.name = changes["name"].strip()
    if changes.get("status") is not None:
        court.status = changes["status"].value
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
    rule.price = float(price)
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
