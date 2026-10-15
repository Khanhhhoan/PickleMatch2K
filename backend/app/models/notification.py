from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base_class import Base


class Notification(Base):
    """
    Thông báo trong ứng dụng, lưu lại để người dùng offline vẫn đọc được sau. Mỗi sự kiện có một event_key: cùng một
    sự kiện chỉ tạo một thông báo cho mỗi người (unique user_id + event_key), nên tác vụ chạy lại không gửi trùng.
    """
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "event_key", name="uq_notifications_user_event"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(40), nullable=False)        # MATCH_CANCELLED, MATCH_REQUEST, MATCH_ACCEPTED, MATCH_REJECTED...
    title = Column(String(160), nullable=False)
    body = Column(String(500), nullable=False)
    link = Column(String(255), nullable=True)        # trang mở ra khi bấm vào thông báo
    event_key = Column(String(120), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
