from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.matching_policy import RECOMMEND_MIN_COMPATIBILITY
from app.core.websocket_manager import dispatch, manager
from app.models.booking import Booking, BookingSource, BookingStatus
from app.models.match import Match, MatchParticipant, MatchStatus, ParticipantStatus
from app.models.user import User
from app.schemas.match import MatchCreate, MatchResponse
from app.utils.timeutils import now_vn, vn_datetime

ACTIVE_MATCH_STATUSES = [MatchStatus.OPEN.value, MatchStatus.FULL.value]


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _notify(match: Match, event: str, message: str) -> None:
    dispatch(manager.broadcast_global({
        "type": event,
        "match_id": match.id,
        "venue_id": match.venue_id,
        "status": match.status,
        "participants_count": len(match.participants),
        "num_players": match.num_players,
        "is_full": match.status == MatchStatus.FULL.value,
        "message": message,
    }))


def serialize_match(match: Match, viewer_id: Optional[int] = None, compatibility: Optional[float] = None) -> MatchResponse:
    """Chuyển Match sang response; số điện thoại chỉ hiện cho thành viên của chính phòng đó."""
    response = MatchResponse.model_validate(match)
    is_member = viewer_id is not None and (
        match.creator_id == viewer_id or any(p.user_id == viewer_id for p in match.participants)
    )
    if not is_member:
        for participant in response.participants:
            participant.phone = None
    response.compatibility = compatibility
    response.is_recommended = compatibility is not None and compatibility >= RECOMMEND_MIN_COMPATIBILITY
    return response


def auto_update_expired_matches(db: Session) -> List[Dict[str, Any]]:
    """Tác vụ nền: phòng đã qua giờ thi đấu -> COMPLETED nếu đủ người, CANCELLED nếu chưa đủ."""
    now_local = now_vn()
    active = db.query(Match).filter(Match.status.in_(ACTIVE_MATCH_STATUSES), Match.date <= now_local.date()).all()
    updated = []
    for match in active:
        if vn_datetime(match.date, match.end_time) > now_local:
            continue
        is_full = match.status == MatchStatus.FULL.value or len(match.participants) >= match.num_players
        match.status = MatchStatus.COMPLETED.value if is_full else MatchStatus.CANCELLED.value
        updated.append(match)
    if updated:
        db.commit()
        for match in updated:
            _notify(match, "MATCH_UPDATED", f"Phòng đấu #{match.id} đã kết thúc.")
    return [{"id": m.id, "status": m.status} for m in updated]


def _match_window_from_booking(booking: Booking):
    """Sân và khoảng giờ liên tục đầu tiên của đơn (đơn 2 giờ liền nhau cho phòng đấu 2 giờ)."""
    details = sorted(booking.details, key=lambda d: (d.date, d.court_id, d.start_time))
    first = details[0]
    end_time = first.end_time
    for detail in details[1:]:
        if detail.court_id == first.court_id and detail.date == first.date and detail.start_time == end_time:
            end_time = detail.end_time
    return first, end_time


def create_match(db: Session, user: User, match_in: MatchCreate) -> Match:
    booking = db.query(Booking).filter(
        Booking.id == match_in.booking_id, Booking.user_id == user.id, Booking.source == BookingSource.ONLINE.value
    ).first()
    if not booking or not booking.details:
        raise _error(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn đặt sân của bạn.")
    if booking.status not in (BookingStatus.CONFIRMED.value, BookingStatus.CHECKED_IN.value):
        raise _error(400, "Chỉ mở được phòng đấu trên đơn đặt sân đã thanh toán cọc và còn hiệu lực.")

    first, end_time = _match_window_from_booking(booking)
    if vn_datetime(first.date, end_time) <= now_vn():
        raise _error(400, "Lịch đặt sân này đã qua giờ thi đấu, không thể mở phòng.")

    already = db.query(Match.id).filter(Match.booking_id == booking.id, Match.status != MatchStatus.CANCELLED.value).first()
    if already:
        raise _error(400, f"Đơn {booking.booking_code} đã có phòng đấu rồi.")

    match = Match(
        creator_id=user.id,
        booking_id=booking.id,
        venue_id=first.court.venue_id,
        court_id=first.court_id,
        date=first.date,
        start_time=first.start_time,
        end_time=end_time,
        required_skill=match_in.required_skill,
        num_players=match_in.num_players,
        purpose=match_in.purpose,
        notes=(match_in.notes or "").strip() or None,
        status=MatchStatus.OPEN.value,
    )
    match.participants.append(MatchParticipant(user_id=user.id, status=ParticipantStatus.ACCEPTED.value))
    db.add(match)
    db.commit()
    db.refresh(match)
    _notify(match, "MATCH_CREATED", f"Phòng đấu mới vừa được mở tại {match.venue_name}.")
    return match


def match_query(db: Session):
    return db.query(Match).options(
        selectinload(Match.creator).selectinload(User.player_profile),
        selectinload(Match.participants).selectinload(MatchParticipant.user).selectinload(User.player_profile),
        selectinload(Match.venue),
        selectinload(Match.court),
        selectinload(Match.booking),
    )


def get_visible_matches(db: Session, current_user_id: Optional[int] = None) -> List[Match]:
    """Phòng đang mở/đã đủ người; người đã đăng nhập còn thấy mọi phòng mình tạo hoặc tham gia."""
    query = match_query(db)
    visible = Match.status.in_(ACTIVE_MATCH_STATUSES)
    if current_user_id:
        visible = or_(
            visible,
            Match.creator_id == current_user_id,
            Match.participants.any(MatchParticipant.user_id == current_user_id),
        )
    return query.filter(visible).order_by(Match.date.desc(), Match.start_time.asc()).all()


def get_match(db: Session, match_id: int, *, for_update: bool = False) -> Match:
    query = db.query(Match).filter(Match.id == match_id)
    if for_update:
        query = query.populate_existing().with_for_update()
    match = query.first()
    if not match:
        raise _error(status.HTTP_404_NOT_FOUND, "Không tìm thấy phòng đấu")
    return match


def join_match(db: Session, match_id: int, user_id: int) -> Match:
    # Khóa dòng phòng đấu để hai người không cùng vào chỗ trống cuối cùng
    match = get_match(db, match_id, for_update=True)
    if match.status != MatchStatus.OPEN.value:
        raise _error(400, "Phòng đấu không còn mở.")
    if vn_datetime(match.date, match.end_time) <= now_vn():
        raise _error(400, "Phòng đấu đã qua giờ thi đấu.")
    if any(p.user_id == user_id for p in match.participants):
        raise _error(400, "Bạn đã ở trong phòng đấu này.")

    accepted = sum(1 for p in match.participants if p.status == ParticipantStatus.ACCEPTED.value)
    if accepted >= match.num_players:
        match.status = MatchStatus.FULL.value
        db.commit()
        raise _error(400, "Phòng đấu đã đủ người.")

    match.participants.append(MatchParticipant(user_id=user_id, status=ParticipantStatus.ACCEPTED.value))
    if accepted + 1 >= match.num_players:
        match.status = MatchStatus.FULL.value
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(400, "Bạn đã ở trong phòng đấu này.")
    db.refresh(match)
    _notify(match, "MATCH_UPDATED", f"Có người vừa tham gia phòng #{match.id} ({len(match.participants)}/{match.num_players}).")
    return match


def leave_match(db: Session, match_id: int, user_id: int) -> Match:
    match = get_match(db, match_id, for_update=True)
    if match.status not in ACTIVE_MATCH_STATUSES:
        raise _error(400, "Phòng đấu đã kết thúc hoặc đã hủy.")
    participant = next((p for p in match.participants if p.user_id == user_id), None)
    if not participant:
        raise _error(400, "Bạn không ở trong phòng đấu này.")

    if match.creator_id == user_id:
        match.status = MatchStatus.CANCELLED.value  # chủ phòng rời đi thì hủy phòng
    else:
        match.participants.remove(participant)
        if match.status == MatchStatus.FULL.value:
            match.status = MatchStatus.OPEN.value
    db.commit()
    db.refresh(match)
    _notify(match, "MATCH_UPDATED", f"Phòng đấu #{match.id} vừa có thay đổi thành viên.")
    return match
