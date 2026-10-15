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


def accepted_participants(match: Match) -> List[MatchParticipant]:
    """Thành viên chính thức của phòng (gồm chủ phòng); yêu cầu chờ duyệt hay bị từ chối không chiếm chỗ."""
    return [p for p in match.participants if p.status == ParticipantStatus.ACCEPTED.value]


def accepted_count(match: Match) -> int:
    return len(accepted_participants(match))


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """0901234233 -> 0901***233: đủ để nhận ra số của ai, không đủ để gọi."""
    value = (phone or "").strip()
    if not value:
        return None
    if len(value) <= 7:
        return f"{value[:2]}***{value[-1:]}"
    return f"{value[:4]}***{value[-3:]}"


def _notify(match: Match, event: str, message: str) -> None:
    dispatch(manager.broadcast_global({
        "type": event,
        "match_id": match.id,
        "venue_id": match.venue_id,
        "status": match.status,
        "participants_count": accepted_count(match),
        "num_players": match.num_players,
        "is_full": match.status == MatchStatus.FULL.value,
        "message": message,
    }))


def serialize_match(match: Match, viewer_id: Optional[int] = None, compatibility: Optional[float] = None) -> MatchResponse:
    """
    Chuyển Match sang response theo quy tắc riêng tư của phòng đấu:
    - Thành viên đã được duyệt (gồm chủ phòng) thấy đủ số điện thoại của nhau.
    - Người khác (chưa vào phòng, đang chờ duyệt, bị từ chối, đã rời phòng) chỉ thấy số đã che, ví dụ 0901***233.
    - Yêu cầu chờ duyệt và bị từ chối chỉ chủ phòng thấy; người gửi yêu cầu thấy dòng của chính mình.
    Việc che làm ở đây, phía máy chủ: số đầy đủ không bao giờ rời API tới người không được xem.
    """
    response = MatchResponse.model_validate(match)
    mine = next((p for p in match.participants if p.user_id == viewer_id), None) if viewer_id is not None else None
    is_host = viewer_id is not None and match.creator_id == viewer_id
    is_member = is_host or (mine is not None and mine.status == ParticipantStatus.ACCEPTED.value)

    visible = []
    for participant in response.participants:
        accepted = participant.status == ParticipantStatus.ACCEPTED.value
        own = participant.user_id == viewer_id
        if not accepted and not is_host and not own:
            continue
        if not own and not (is_member and accepted):
            participant.phone = mask_phone(participant.phone)
        visible.append(participant)
    response.participants = visible
    response.accepted_count = accepted_count(match)
    response.my_status = mine.status if mine else None
    response.pending_count = (
        sum(1 for p in match.participants if p.status == ParticipantStatus.PENDING.value) if is_host else 0
    )
    response.compatibility = compatibility
    response.is_recommended = compatibility is not None and compatibility >= RECOMMEND_MIN_COMPATIBILITY
    return response


def auto_update_expired_matches(db: Session) -> List[Dict[str, Any]]:
    """
    Tác vụ nền: phòng đã qua giờ thi đấu -> COMPLETED nếu đủ người, CANCELLED nếu chưa đủ.
    Khóa dòng với SKIP LOCKED để hai lượt chạy song song không xử lý (và thông báo) một phòng hai lần.
    """
    now_local = now_vn()
    active = (
        db.query(Match)
        .filter(Match.status.in_(ACTIVE_MATCH_STATUSES), Match.date <= now_local.date())
        .with_for_update(skip_locked=True)
        .all()
    )
    updated = []
    for match in active:
        if vn_datetime(match.date, match.end_time) > now_local:
            continue
        is_full = match.status == MatchStatus.FULL.value or accepted_count(match) >= match.num_players
        match.status = MatchStatus.COMPLETED.value if is_full else MatchStatus.CANCELLED.value
        updated.append(match)
    if updated:
        db.commit()
        for match in updated:
            _notify(match, "MATCH_UPDATED", f"Phòng đấu #{match.id} đã kết thúc.")
    return [{"id": m.id, "status": m.status} for m in updated]


def _reject_time_clash(db: Session, user_id: int, day, start_time, end_time, *, exclude_id: Optional[int] = None,
                       who: str = "Bạn") -> None:
    """
    Một người không thể chơi ở hai nơi cùng lúc: từ chối nếu người này đã là thành viên (được duyệt) của một phòng
    còn hoạt động khác trùng khoảng giờ. Yêu cầu còn chờ duyệt không tính. Khóa dòng người chơi trước để hai yêu cầu
    đồng thời của cùng một người không cùng lọt qua.
    """
    db.query(User.id).filter(User.id == user_id).with_for_update().first()
    query = (
        db.query(Match)
        .join(MatchParticipant, MatchParticipant.match_id == Match.id)
        .filter(
            MatchParticipant.user_id == user_id,
            MatchParticipant.status == ParticipantStatus.ACCEPTED.value,
            Match.status.in_(ACTIVE_MATCH_STATUSES),
            Match.date == day,
            Match.start_time < end_time,
            Match.end_time > start_time,
        )
    )
    if exclude_id is not None:
        query = query.filter(Match.id != exclude_id)
    clash = query.first()
    if clash:
        raise _error(
            400,
            f"{who} đang ở trong một phòng đấu khác trùng giờ ({clash.start_time:%H:%M} - {clash.end_time:%H:%M} tại {clash.venue_name}).",
        )


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
    _reject_time_clash(db, user.id, first.date, first.start_time, end_time)

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


def _ensure_open_and_upcoming(match: Match) -> None:
    if match.status != MatchStatus.OPEN.value:
        raise _error(400, "Phòng đấu không còn mở." if match.status != MatchStatus.FULL.value else "Phòng đấu đã đủ người.")
    if vn_datetime(match.date, match.end_time) <= now_vn():
        raise _error(400, "Phòng đấu đã qua giờ thi đấu.")


def join_match(db: Session, match_id: int, user_id: int) -> Match:
    """
    Người chơi xin vào phòng: tạo yêu cầu chờ chủ phòng duyệt. Yêu cầu chưa chiếm chỗ và chưa cho xem số điện
    thoại của ai; mỗi người chỉ có một yêu cầu cho một phòng, bị từ chối thì không gửi lại được.
    """
    # Khóa dòng phòng đấu để các thay đổi thành viên của cùng một phòng diễn ra lần lượt
    match = get_match(db, match_id, for_update=True)
    existing = next((p for p in match.participants if p.user_id == user_id), None)
    if existing is not None:
        if existing.status == ParticipantStatus.ACCEPTED.value:
            raise _error(400, "Bạn đã ở trong phòng đấu này.")
        if existing.status == ParticipantStatus.PENDING.value:
            raise _error(400, "Bạn đã gửi yêu cầu tham gia phòng này, hãy chờ chủ phòng duyệt.")
        raise _error(400, "Chủ phòng đã từ chối yêu cầu tham gia của bạn.")
    _ensure_open_and_upcoming(match)
    _reject_time_clash(db, user_id, match.date, match.start_time, match.end_time, exclude_id=match.id)
    if accepted_count(match) >= match.num_players:
        raise _error(400, "Phòng đấu đã đủ người.")

    match.participants.append(MatchParticipant(user_id=user_id, status=ParticipantStatus.PENDING.value))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _error(400, "Bạn đã gửi yêu cầu tham gia phòng này, hãy chờ chủ phòng duyệt.")
    db.refresh(match)
    _notify(match, "MATCH_UPDATED", f"Phòng #{match.id} vừa có người xin tham gia.")
    return match


def decide_join_request(db: Session, match_id: int, host_id: int, user_id: int, *, accept: bool) -> Match:
    """Chủ phòng chấp nhận hoặc từ chối một yêu cầu tham gia đang chờ duyệt."""
    match = get_match(db, match_id, for_update=True)
    if match.creator_id != host_id:
        raise _error(status.HTTP_403_FORBIDDEN, "Chỉ chủ phòng mới duyệt được yêu cầu tham gia.")
    request = next(
        (p for p in match.participants if p.user_id == user_id and p.status == ParticipantStatus.PENDING.value), None
    )
    if request is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Không tìm thấy yêu cầu tham gia đang chờ duyệt.")

    if accept:
        _ensure_open_and_upcoming(match)
        if accepted_count(match) >= match.num_players:
            raise _error(400, "Phòng đấu đã đủ người.")
        _reject_time_clash(db, user_id, match.date, match.start_time, match.end_time, exclude_id=match.id,
                           who="Người chơi này")
        request.status = ParticipantStatus.ACCEPTED.value
        if accepted_count(match) >= match.num_players:
            match.status = MatchStatus.FULL.value
    else:
        request.status = ParticipantStatus.REJECTED.value
    db.commit()
    db.refresh(match)
    _notify(match, "MATCH_UPDATED", f"Phòng đấu #{match.id} vừa có thay đổi thành viên.")
    return match


def leave_match(db: Session, match_id: int, user_id: int) -> Match:
    """Rời phòng (thành viên) hoặc rút yêu cầu tham gia (đang chờ duyệt). Chủ phòng rời đi thì phòng bị hủy."""
    match = get_match(db, match_id, for_update=True)
    if match.status not in ACTIVE_MATCH_STATUSES:
        raise _error(400, "Phòng đấu đã kết thúc hoặc đã hủy.")
    participant = next(
        (p for p in match.participants
         if p.user_id == user_id and p.status in (ParticipantStatus.ACCEPTED.value, ParticipantStatus.PENDING.value)),
        None,
    )
    if not participant:
        raise _error(400, "Bạn không ở trong phòng đấu này.")

    if match.creator_id == user_id:
        match.status = MatchStatus.CANCELLED.value  # chủ phòng rời đi thì hủy phòng
    else:
        was_member = participant.status == ParticipantStatus.ACCEPTED.value
        match.participants.remove(participant)
        if was_member and match.status == MatchStatus.FULL.value:
            match.status = MatchStatus.OPEN.value
    db.commit()
    db.refresh(match)
    _notify(match, "MATCH_UPDATED", f"Phòng đấu #{match.id} vừa có thay đổi thành viên.")
    return match
