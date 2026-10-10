from datetime import date, datetime, time, timezone
from typing import List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.core.booking_policy import MAX_SLOTS_PER_BOOKING

# Trường tên "date" có giá trị mặc định sẽ che mất kiểu date trong thân lớp, nên dùng bí danh cho kiểu.
DateType = date


def _blank_to_none(value):
    if isinstance(value, str) and not value.strip():
        return None
    return value


class BookingDetailCreate(BaseModel):
    court_id: int
    date: date
    start_time: time
    end_time: time


class BookingCreate(BaseModel):
    details: List[BookingDetailCreate] = Field(min_length=1, max_length=MAX_SLOTS_PER_BOOKING)


class DeskBookingCreate(BaseModel):
    """
    Đơn do nhân viên/chủ sân tạo tại quầy cho khách vãng lai. Chấp nhận cả hai bộ tên trường
    đang dùng ở cổng chủ sân (date, customer_name...) và cổng nhân viên (booking_date, guest_name...).
    """
    court_id: int
    date: DateType = Field(validation_alias=AliasChoices("date", "booking_date"))
    start_time: time
    end_time: time
    customer_name: Optional[str] = Field(default=None, max_length=120, validation_alias=AliasChoices("customer_name", "guest_name"))
    customer_phone: Optional[str] = Field(default=None, max_length=20, validation_alias=AliasChoices("customer_phone", "guest_phone"))
    # Tổng tiền thỏa thuận; bỏ trống hoặc 0 để hệ thống tự tính theo bảng giá
    price: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    # FULLY_PAID | DEPOSIT_PAID | UNPAID, hoặc CASH | BANK_TRANSFER (đã thu đủ bằng phương thức đó)
    payment_method: Literal["FULLY_PAID", "DEPOSIT_PAID", "UNPAID", "CASH", "BANK_TRANSFER"] = "CASH"

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    _blank = field_validator("customer_name", "customer_phone", "price", mode="before")(_blank_to_none)


class HoldSlotRequest(BaseModel):
    venue_id: int
    court_id: int
    court_name: Optional[str] = None
    date: date
    start_time: time
    end_time: time


class ReleaseSlotRequest(BaseModel):
    venue_id: int
    court_id: int
    date: date
    start_time: time

    model_config = ConfigDict(extra="ignore")


class BookingStatusUpdate(BaseModel):
    """Tương thích ngược: chỉ nhận các chuyển trạng thái hợp lệ (xem endpoint PUT /bookings/{id}/status)."""
    status: Literal["CHECKED_IN", "COMPLETED", "CANCELLED"]
    reason: Optional[str] = Field(default=None, max_length=300)

    model_config = ConfigDict(extra="ignore")


class CheckInRequest(BaseModel):
    # Số tiền thu khi khách nhận sân; bỏ trống = thu toàn bộ phần còn lại, 0 = thu sau
    collected_amount: Optional[float] = Field(default=None, ge=0)
    payment_method: Literal["CASH", "BANK_TRANSFER"] = "CASH"


class CollectPaymentRequest(BaseModel):
    amount: float = Field(gt=0)
    payment_method: Literal["CASH", "BANK_TRANSFER"] = "CASH"


class RescheduleRequest(BaseModel):
    court_id: Optional[int] = None
    booking_date: Optional[date] = Field(default=None, validation_alias=AliasChoices("booking_date", "date"))
    start_time: Optional[time] = None

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    _blank = field_validator("court_id", "booking_date", "start_time", mode="before")(_blank_to_none)


class CancelBookingRequest(BaseModel):
    bank_account: Optional[str] = Field(default=None, max_length=40)
    bank_name: Optional[str] = Field(default=None, max_length=80)
    account_holder: Optional[str] = Field(default=None, max_length=120)
    reason: Optional[str] = Field(default=None, max_length=300)


class ConfirmRefundRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=300)


class CancelPreviewResponse(BaseModel):
    booking_id: int
    can_cancel: bool
    tier: str  # UNPAID | FULL_REFUND | RESCHEDULE_ONLY | NO_REFUND | NOT_ALLOWED
    hours_before: float
    paid_amount: float
    refund_amount: float
    full_refund_hours: int
    reschedule_hours: int
    message: str


class BookingDetailResponse(BaseModel):
    id: int
    court_id: int
    date: date
    start_time: time
    end_time: time
    price: float
    is_active: bool = True
    court_name: Optional[str] = None
    venue_id: Optional[int] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BookingResponse(BaseModel):
    id: int
    booking_code: Optional[str] = None
    user_id: int
    source: Optional[str] = "ONLINE"
    total_price: float
    deposit_amount: float = 0.0
    paid_amount: float = 0.0
    remaining_amount: float = 0.0
    status: str
    payment_status: Optional[str] = "UNPAID"
    expires_at: Optional[datetime] = None
    checked_in_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    refund_status: Optional[str] = None
    refund_amount: Optional[float] = 0.0
    refund_bank_account: Optional[str] = None
    refund_bank_name: Optional[str] = None
    refund_account_holder: Optional[str] = None
    refund_reason: Optional[str] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime
    details: List[BookingDetailResponse]
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_email: Optional[str] = None

    @field_serializer("created_at", "refunded_at", "expires_at", "checked_in_at", "cancelled_at", when_used="json")
    def serialize_datetime(self, v: Optional[datetime]) -> Optional[str]:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()

    model_config = ConfigDict(from_attributes=True)
