import enum
import json
from datetime import date
from typing import List, Optional

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class UserRole(str, enum.Enum):
    PLAYER = "PLAYER"
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    STAFF = "STAFF"


def _load_json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default=UserRole.PLAYER.value, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Hồ sơ thuộc về tài khoản: xóa tài khoản thì xóa luôn hồ sơ
    player_profile = relationship("PlayerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    owner_profile = relationship("OwnerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    staff_profile = relationship("StaffProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")


class PlayerProfile(Base):
    __tablename__ = "player_profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    skill_level = Column(Float, nullable=True)        # Trình độ DUPR tự khai (1.0 - 8.0)
    play_style = Column(String, nullable=True)
    matches_played = Column(Integer, nullable=True, default=0)
    matches_won = Column(Integer, nullable=True, default=0)
    date_of_birth = Column(Date, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    # Dữ liệu phục vụ gợi ý sân và ghép người chơi
    purpose = Column(String, nullable=True)            # recreational | practice | competitive
    preferred_amenities = Column(String, nullable=True)  # JSON: danh sách id tiện ích ưa thích
    budget_max = Column(Float, nullable=True)          # Ngân sách tối đa mỗi giờ thuê sân (VNĐ)

    user = relationship("User", back_populates="player_profile")

    @property
    def win_rate(self) -> Optional[float]:
        """Tỷ lệ thắng (%) tự khai; None khi chưa có trận nào."""
        if self.matches_played and self.matches_played > 0:
            return round(((self.matches_won or 0) / self.matches_played) * 100, 1)
        return None

    @property
    def age(self) -> Optional[int]:
        if not self.date_of_birth:
            return None
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    @property
    def preferred_amenity_ids(self) -> List[int]:
        ids = []
        for item in _load_json_list(self.preferred_amenities):
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return ids


class OwnerProfile(Base):
    __tablename__ = "owner_profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    bank_account = Column(String, nullable=True)

    user = relationship("User", back_populates="owner_profile")


class StaffProfile(Base):
    __tablename__ = "staff_profiles"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=True)
    full_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    user = relationship("User", back_populates="staff_profile")
    venue = relationship("Venue")

    @property
    def venue_name(self) -> Optional[str]:
        return self.venue.name if self.venue else None

    @property
    def owner_id(self) -> Optional[int]:
        return self.venue.owner_id if self.venue else None

    @property
    def owner_name(self) -> Optional[str]:
        if self.venue and self.venue.owner:
            profile = self.venue.owner.owner_profile
            return profile.full_name if profile and profile.full_name else None
        return None


# Ensure Venue is registered in SQLAlchemy mapper registry
import app.models.venue  # noqa: E402,F401
