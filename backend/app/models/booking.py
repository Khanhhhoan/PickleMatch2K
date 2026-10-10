import enum

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Time, text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"        # Vừa tạo, đang giữ slot chờ thanh toán cọc (đến expires_at)
    CONFIRMED = "CONFIRMED"    # Đã nhận đủ tiền cọc, hoặc đơn do nhân viên tạo tại quầy
    CHECKED_IN = "CHECKED_IN"  # Khách đã nhận sân
    COMPLETED = "COMPLETED"    # Đã chơi xong
    NO_SHOW = "NO_SHOW"        # Đã cọc nhưng không đến nhận sân
    CANCELLED = "CANCELLED"    # Bị hủy bởi người chơi hoặc cụm sân
    EXPIRED = "EXPIRED"        # Quá hạn thanh toán cọc, slot đã được trả lại


class PaymentStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIALLY_PAID = "PARTIALLY_PAID"  # Đã chuyển nhưng chưa đủ tiền cọc
    DEPOSIT_PAID = "DEPOSIT_PAID"
    FULLY_PAID = "FULLY_PAID"


class RefundStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class BookingSource(str, enum.Enum):
    ONLINE = "ONLINE"  # Người chơi tự đặt trên web
    DESK = "DESK"      # Nhân viên/chủ sân tạo tại quầy cho khách vãng lai


# Trạng thái mà đơn còn chiếm slot trên lịch sân
SLOT_HOLDING_STATUSES = (
    BookingStatus.PENDING.value,
    BookingStatus.CONFIRMED.value,
    BookingStatus.CHECKED_IN.value,
    BookingStatus.COMPLETED.value,
    BookingStatus.NO_SHOW.value,
)
# Trạng thái kết thúc, không còn chuyển tiếp
FINAL_STATUSES = (
    BookingStatus.COMPLETED.value,
    BookingStatus.NO_SHOW.value,
    BookingStatus.CANCELLED.value,
    BookingStatus.EXPIRED.value,
)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String(32), unique=True, index=True, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String, default=BookingSource.ONLINE.value, server_default=BookingSource.ONLINE.value, nullable=False)
    guest_name = Column(String, nullable=True)   # Khách vãng lai của đơn tại quầy
    guest_phone = Column(String, nullable=True)

    total_price = Column(Float, nullable=False, default=0.0)
    deposit_amount = Column(Float, nullable=False, default=0.0, server_default=text("0"))
    paid_amount = Column(Float, nullable=False, default=0.0, server_default=text("0"))
    status = Column(String, default=BookingStatus.PENDING.value, index=True)
    payment_status = Column(String, default=PaymentStatus.UNPAID.value, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Hạn thanh toán cọc của đơn PENDING

    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    checked_in_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancel_reason = Column(String, nullable=True)

    refund_status = Column(String, nullable=True, index=True)  # PENDING, COMPLETED, REJECTED
    refund_amount = Column(Float, nullable=True, default=0.0)
    refund_bank_account = Column(String, nullable=True)
    refund_bank_name = Column(String, nullable=True)
    refund_account_holder = Column(String, nullable=True)
    refund_reason = Column(String, nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    refunded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    details = relationship(
        "BookingDetail", back_populates="booking", cascade="all, delete-orphan",
        order_by="BookingDetail.date, BookingDetail.start_time",
    )
    user = relationship("User", foreign_keys=[user_id])

    @property
    def is_desk_booking(self) -> bool:
        return self.source == BookingSource.DESK.value

    @property
    def user_name(self) -> str:
        if self.guest_name:
            return self.guest_name
        if self.is_desk_booking:
            return "Khách tại quầy"
        if self.user:
            if self.user.player_profile and self.user.player_profile.full_name:
                return self.user.player_profile.full_name
            if self.user.owner_profile and self.user.owner_profile.full_name:
                return self.user.owner_profile.full_name
            if self.user.email:
                return self.user.email.split("@")[0]
        return f"Khách #{self.user_id}"

    @property
    def user_phone(self) -> str:
        if self.is_desk_booking:
            return self.guest_phone or ""
        if self.user:
            if self.user.player_profile and self.user.player_profile.phone:
                return self.user.player_profile.phone
            if self.user.owner_profile and self.user.owner_profile.phone:
                return self.user.owner_profile.phone
        return ""

    @property
    def user_email(self) -> str:
        if self.is_desk_booking:
            return ""
        return self.user.email if self.user and self.user.email else ""

    @property
    def remaining_amount(self) -> float:
        return max(0.0, float(self.total_price or 0) - float(self.paid_amount or 0))

    @property
    def venue_id(self):
        first = self.details[0] if self.details else None
        return first.court.venue_id if first and first.court else None


class BookingDetail(Base):
    """Một dòng = một khung giờ 60 phút của một sân."""
    __tablename__ = "booking_details"
    __table_args__ = (
        Index("ix_booking_details_court_date", "court_id", "date"),
        # Một slot chỉ thuộc về một đơn còn hiệu lực. Trên PostgreSQL còn có ràng buộc loại trừ
        # ex_booking_details_no_overlap (xem migration 0003) chặn mọi khoảng thời gian chồng lấn.
        Index(
            "uq_booking_details_active_slot", "court_id", "date", "start_time",
            unique=True, postgresql_where=text("is_active"), sqlite_where=text("is_active"),
        ),
        CheckConstraint("end_time > start_time", name="ck_booking_details_time_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    court_id = Column(Integer, ForeignKey("courts.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    price = Column(Float, nullable=False)
    # False khi đơn bị hủy hoặc hết hạn: slot được trả lại cho người khác đặt
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))

    booking = relationship("Booking", back_populates="details")
    court = relationship("Court")

    @property
    def court_name(self) -> str:
        return self.court.name if self.court else f"Sân #{self.court_id}"

    @property
    def venue_id(self) -> int:
        return self.court.venue_id if self.court else 0

    @property
    def venue_name(self) -> str:
        return self.court.venue.name if self.court and self.court.venue else ""

    @property
    def venue_address(self) -> str:
        return self.court.venue.address if self.court and self.court.venue else ""
