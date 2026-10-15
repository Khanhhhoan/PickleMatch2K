"""Thông báo trong ứng dụng của người đang đăng nhập: xem, đánh dấu đã đọc. Mỗi người chỉ thấy thông báo của mình."""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_serializer
from sqlalchemy.orm import Session

from app.api import deps
from app.models.notification import Notification
from app.models.user import User
from app.utils.timeutils import now_utc

router = APIRouter()


class NotificationResponse(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    link: Optional[str] = None
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "read_at", when_used="json")
    def _utc(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


class NotificationListResponse(BaseModel):
    unread_count: int
    items: List[NotificationResponse]


def _mine(db: Session, user: User):
    return db.query(Notification).filter(Notification.user_id == user.id)


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Thông báo mới nhất trước, kèm số thông báo chưa đọc."""
    items = _mine(db, current_user).order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
    unread = _mine(db, current_user).filter(Notification.read_at.is_(None)).count()
    return {"unread_count": unread, "items": items}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    notification = _mine(db, current_user).filter(Notification.id == notification_id).first()
    if notification is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy thông báo.")
    if notification.read_at is None:
        notification.read_at = now_utc()
        db.commit()
        db.refresh(notification)
    return notification


@router.post("/read-all")
def mark_all_read(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_active_user)):
    updated = _mine(db, current_user).filter(Notification.read_at.is_(None)).update(
        {Notification.read_at: now_utc()}, synchronize_session=False)
    db.commit()
    return {"updated": updated}
