import enum

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, Table, Time, UniqueConstraint, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class VenueStatus(str, enum.Enum):
    PENDING = "PENDING"          # Chủ sân vừa đăng ký, chờ Admin duyệt
    ACTIVE = "ACTIVE"            # Đang hoạt động, hiển thị công khai
    INACTIVE = "INACTIVE"        # Ngừng hoạt động
    MAINTENANCE = "MAINTENANCE"  # Tạm đóng bảo trì
    REJECTED = "REJECTED"        # Admin từ chối


class CourtStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    MAINTENANCE = "MAINTENANCE"


class PriceRuleType(str, enum.Enum):
    BASE = "BASE"
    PEAK = "PEAK"
    WEEKEND = "WEEKEND"


venue_amenities = Table(
    "venue_amenities", Base.metadata,
    Column("venue_id", Integer, ForeignKey("venues.id"), primary_key=True),
    Column("amenity_id", Integer, ForeignKey("amenities.id"), primary_key=True),
)


class Amenity(Base):
    __tablename__ = "amenities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    icon = Column(String, nullable=True)


class Venue(Base):
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    address = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    google_maps_url = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    images = Column(String, nullable=True)  # JSON-encoded array of image URLs
    status = Column(String, default=VenueStatus.ACTIVE.value)
    # Đơn tại quầy chưa thu đồng nào tự hủy khi còn bấy nhiêu phút nữa tới giờ chơi; 0 = không tự hủy
    unpaid_desk_release_minutes = Column(Integer, nullable=False, default=30, server_default=text("30"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User")
    courts = relationship("Court", back_populates="venue", cascade="all, delete-orphan", order_by="Court.id")
    amenities = relationship("Amenity", secondary=venue_amenities, order_by="Amenity.id")
    operating_hours = relationship(
        "OperatingHour", back_populates="venue", cascade="all, delete-orphan", order_by="OperatingHour.day_of_week"
    )
    price_rules = relationship("PriceRule", back_populates="venue", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="venue", cascade="all, delete-orphan")


class Court(Base):
    __tablename__ = "courts"

    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, default=CourtStatus.ACTIVE.value)
    price = Column(BigInteger, nullable=True)  # Giá riêng của sân (VNĐ/giờ, số nguyên); NULL = dùng bảng giá cụm sân

    venue = relationship("Venue", back_populates="courts")


class OperatingHour(Base):
    __tablename__ = "operating_hours"
    __table_args__ = (
        UniqueConstraint("venue_id", "day_of_week", name="uq_operating_hours_venue_day"),
    )

    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    open_time = Column(Time, nullable=False)
    close_time = Column(Time, nullable=False)

    venue = relationship("Venue", back_populates="operating_hours")


class PriceRule(Base):
    __tablename__ = "price_rules"

    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    rule_type = Column(String, default=PriceRuleType.BASE.value)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    price = Column(BigInteger, nullable=False)  # VNĐ/giờ, số nguyên

    venue = relationship("Venue", back_populates="price_rules")


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "venue_id", name="uq_reviews_user_venue"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False, index=True)
    rating = Column(Float, nullable=False, default=5.0)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    venue = relationship("Venue", back_populates="reviews")
    user = relationship("User")
