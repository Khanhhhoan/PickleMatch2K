import enum
from typing import Optional

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class MatchStatus(str, enum.Enum):
    OPEN = "OPEN"
    FULL = "FULL"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class ParticipantStatus(str, enum.Enum):
    INVITED = "INVITED"
    PENDING = "PENDING"    # Đã xin tham gia, chờ chủ phòng duyệt: chưa chiếm chỗ, chưa xem được số điện thoại
    ACCEPTED = "ACCEPTED"  # Thành viên chính thức (chủ phòng luôn ở trạng thái này)
    REJECTED = "REJECTED"  # Chủ phòng đã từ chối: không gửi lại yêu cầu cho phòng này được


def _display_name(user, fallback: str) -> str:
    """Tên hiển thị công khai: không bao giờ trả về email đầy đủ."""
    if user is None:
        return fallback
    if user.player_profile and user.player_profile.full_name:
        return user.player_profile.full_name
    if user.owner_profile and user.owner_profile.full_name:
        return user.owner_profile.full_name
    return fallback


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    court_id = Column(Integer, ForeignKey("courts.id"), nullable=True, index=True)
    # Đơn đặt sân bảo đảm có sân cho phòng đấu này
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True, index=True)
    date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    required_skill = Column(Float, nullable=True)
    num_players = Column(Integer, nullable=False, default=4)
    purpose = Column(String, nullable=True)  # recreational, practice, competitive
    status = Column(String, default=MatchStatus.OPEN.value, index=True)
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    participants = relationship("MatchParticipant", back_populates="match", cascade="all, delete-orphan")
    creator = relationship("User")
    court = relationship("Court")
    venue = relationship("Venue")
    booking = relationship("Booking")

    @property
    def court_name(self) -> Optional[str]:
        if self.court and self.court.name:
            return self.court.name
        return f"Sân #{self.court_id}" if self.court_id else None

    @property
    def creator_name(self) -> str:
        return _display_name(self.creator, f"Người chơi #{self.creator_id}")

    @property
    def creator_skill_level(self) -> Optional[float]:
        profile = self.creator.player_profile if self.creator else None
        return profile.skill_level if profile else None

    @property
    def creator_play_style(self) -> Optional[str]:
        profile = self.creator.player_profile if self.creator else None
        return profile.play_style if profile else None

    @property
    def venue_name(self) -> str:
        return self.venue.name if self.venue and self.venue.name else ""

    @property
    def booking_code(self) -> Optional[str]:
        return self.booking.booking_code if self.booking else None


class MatchParticipant(Base):
    __tablename__ = "match_participants"
    __table_args__ = (
        UniqueConstraint("match_id", "user_id", name="uq_match_participants_match_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String, default=ParticipantStatus.ACCEPTED.value)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    match = relationship("Match", back_populates="participants")
    user = relationship("User")

    @property
    def user_name(self) -> str:
        return _display_name(self.user, f"Người chơi #{self.user_id}")

    @property
    def skill_level(self) -> Optional[float]:
        profile = self.user.player_profile if self.user else None
        return profile.skill_level if profile else None

    @property
    def play_style(self) -> Optional[str]:
        profile = self.user.player_profile if self.user else None
        return profile.play_style if profile else None

    @property
    def phone(self) -> str:
        profile = self.user.player_profile if self.user else None
        return profile.phone if profile and profile.phone else ""
