from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.match import Match, MatchParticipant, MatchStatus, ParticipantStatus
from app.models.user import User, UserRole
from app.models.venue import Court, Venue
from app.schemas.match import (
    AddParticipantRequest,
    MatchAdminCreate,
    MatchAdminUpdate,
    MatchCreate,
    MatchResponse,
    MatchStatusUpdate,
)
from app.services import match_service, ml_service, notification_service

router = APIRouter()

admin_only = deps.RoleChecker([UserRole.ADMIN.value])


def _admin_view(match: Match) -> MatchResponse:
    """Admin xem được số điện thoại thành viên để hỗ trợ xử lý."""
    return match_service.serialize_match(match, viewer_id=match.creator_id)


@router.post("", response_model=MatchResponse)
def create_match(
    match_in: MatchCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Mở phòng đấu trên một đơn đặt sân đã thanh toán cọc của chính mình. Chủ phòng tự động tham gia."""
    match = match_service.create_match(db, current_user, match_in)
    return match_service.serialize_match(match, current_user.id)


@router.get("", response_model=List[MatchResponse])
def read_open_matches(
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_user_optional),
):
    """
    Phòng đang mở (công khai) và các phòng của người đang đăng nhập. Với người đã đăng nhập,
    mỗi phòng kèm `compatibility`: độ phù hợp do mô hình Random Forest ước lượng.
    Truyền latitude/longitude hiện tại để tính khoảng cách tới sân chính xác hơn vị trí trong hồ sơ.
    """
    matches = match_service.get_visible_matches(db, current_user.id if current_user else None)
    scores = ml_service.match_compatibility(current_user, matches, latitude, longitude) if current_user else {}
    viewer_id = current_user.id if current_user else None
    return [match_service.serialize_match(m, viewer_id, scores.get(m.id)) for m in matches]


@router.post("/{match_id}/join", response_model=MatchResponse)
def join_match(match_id: int, db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_active_user)):
    """Xin tham gia phòng đấu: yêu cầu chờ chủ phòng duyệt (my_status = PENDING)."""
    return match_service.serialize_match(match_service.join_match(db, match_id, current_user.id), current_user.id)


@router.post("/{match_id}/requests/{user_id}/accept", response_model=MatchResponse)
def accept_join_request(
    match_id: int, user_id: int, db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Chủ phòng chấp nhận một yêu cầu tham gia: người đó thành thành viên và thấy số điện thoại của các thành viên."""
    match = match_service.decide_join_request(db, match_id, current_user.id, user_id, accept=True)
    return match_service.serialize_match(match, current_user.id)


@router.post("/{match_id}/requests/{user_id}/reject", response_model=MatchResponse)
def reject_join_request(
    match_id: int, user_id: int, db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Chủ phòng từ chối một yêu cầu tham gia; người đó không gửi lại yêu cầu cho phòng này được."""
    match = match_service.decide_join_request(db, match_id, current_user.id, user_id, accept=False)
    return match_service.serialize_match(match, current_user.id)


@router.post("/{match_id}/leave", response_model=MatchResponse)
def leave_match(match_id: int, db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_active_user)):
    """Rời phòng đấu, hoặc rút yêu cầu tham gia đang chờ duyệt. Nếu chủ phòng rời đi thì phòng bị hủy."""
    return match_service.serialize_match(match_service.leave_match(db, match_id, current_user.id), current_user.id)


# ==========================================
# ADMIN
# ==========================================

@router.get("/admin/all", response_model=List[MatchResponse])
def get_all_matches_admin(
    status: Optional[str] = None,
    venue_id: Optional[int] = None,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    query = match_service.match_query(db)
    if status and status != "ALL":
        query = query.filter(Match.status == status)
    if venue_id:
        query = query.filter(Match.venue_id == venue_id)
    return [_admin_view(m) for m in query.order_by(Match.date.desc(), Match.start_time.desc()).all()]


@router.post("/admin/create", response_model=MatchResponse)
def create_match_admin(
    match_in: MatchAdminCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(admin_only),
):
    """Admin tạo phòng đấu trực tiếp tại một cụm sân (không bắt buộc gắn đơn đặt)."""
    if not db.query(Venue.id).filter(Venue.id == match_in.venue_id).first():
        raise HTTPException(status_code=404, detail="Không tìm thấy cụm sân")
    if match_in.court_id:
        court = db.query(Court).filter(Court.id == match_in.court_id).first()
        if not court or court.venue_id != match_in.venue_id:
            raise HTTPException(status_code=400, detail="Sân không thuộc cụm sân đã chọn")
    creator_id = match_in.creator_id or current_user.id
    if not db.query(User.id).filter(User.id == creator_id).first():
        raise HTTPException(status_code=404, detail="Không tìm thấy người tạo phòng")

    data = match_in.model_dump(exclude={"creator_id", "status"})
    match = Match(**data, creator_id=creator_id, status=match_in.status.value)
    match.participants.append(MatchParticipant(user_id=creator_id, status=ParticipantStatus.ACCEPTED.value))
    db.add(match)
    db.commit()
    db.refresh(match)
    return _admin_view(match)


@router.put("/admin/{match_id}/status", response_model=MatchResponse)
def update_match_status_admin(
    match_id: int,
    payload: MatchStatusUpdate,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    match = match_service.get_match(db, match_id, for_update=True)
    was_active = match.status in match_service.ACTIVE_MATCH_STATUSES
    match.status = payload.status.value
    if was_active and match.status == MatchStatus.CANCELLED.value:
        notification_service.notify_match_cancelled(db, match, "quản trị viên đã hủy phòng")
    db.commit()
    db.refresh(match)
    return _admin_view(match)


@router.put("/admin/{match_id}", response_model=MatchResponse)
def update_match_admin(
    match_id: int,
    match_update: MatchAdminUpdate,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    match = match_service.get_match(db, match_id)
    changes = match_update.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value
    for field, value in changes.items():
        setattr(match, field, value)
    if match.end_time <= match.start_time:
        raise HTTPException(status_code=400, detail="Giờ kết thúc phải sau giờ bắt đầu.")
    db.commit()
    db.refresh(match)
    return _admin_view(match)


@router.post("/admin/{match_id}/participants", response_model=MatchResponse)
def add_participant_admin(
    match_id: int,
    payload: AddParticipantRequest,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    match = match_service.get_match(db, match_id, for_update=True)
    if not db.query(User.id).filter(User.id == payload.user_id).first():
        raise HTTPException(status_code=404, detail="Không tìm thấy người chơi")
    if any(p.user_id == payload.user_id for p in match.participants):
        raise HTTPException(status_code=400, detail="Người chơi này đã có trong phòng đấu")
    accepted = sum(1 for p in match.participants if p.status == ParticipantStatus.ACCEPTED.value)
    if accepted >= match.num_players:
        raise HTTPException(status_code=400, detail="Phòng đấu đã đủ người")

    match.participants.append(MatchParticipant(user_id=payload.user_id, status=ParticipantStatus.ACCEPTED.value))
    if accepted + 1 >= match.num_players and match.status == MatchStatus.OPEN.value:
        match.status = MatchStatus.FULL.value
    db.commit()
    db.refresh(match)
    return _admin_view(match)


@router.delete("/admin/{match_id}/participants/{user_id}", response_model=MatchResponse)
def remove_participant_admin(
    match_id: int,
    user_id: int,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    match = match_service.get_match(db, match_id, for_update=True)
    participant = next((p for p in match.participants if p.user_id == user_id), None)
    if not participant:
        raise HTTPException(status_code=404, detail="Người chơi không có trong phòng đấu này")
    was_member = participant.status == ParticipantStatus.ACCEPTED.value
    match.participants.remove(participant)
    if was_member and match.status == MatchStatus.FULL.value:
        match.status = MatchStatus.OPEN.value
    db.commit()
    db.refresh(match)
    return _admin_view(match)


@router.delete("/admin/{match_id}")
def delete_match_admin(match_id: int, db: Session = Depends(deps.get_db), _: User = Depends(admin_only)):
    match = match_service.get_match(db, match_id)
    db.delete(match)
    db.commit()
    return {"status": "success", "message": f"Đã xóa phòng đấu #{match_id}"}
