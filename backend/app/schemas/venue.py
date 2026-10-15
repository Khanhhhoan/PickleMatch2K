from datetime import date, datetime, time
from typing import List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.venue import CourtStatus, PriceRuleType, VenueStatus


# Court Schemas
class CourtBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    status: str = CourtStatus.ACTIVE.value
    price: Optional[float] = Field(default=None, ge=0)


class CourtCreate(CourtBase):
    model_config = ConfigDict(extra="ignore")

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str) -> str:
        return CourtStatus(value).value


class CourtUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    status: Optional[CourtStatus] = None
    # Giá riêng của sân (VNĐ/giờ); gửi 0 hoặc null để dùng bảng giá chung của cụm sân
    price: Optional[float] = Field(default=None, ge=0)


class CourtResponse(BaseModel):
    id: int
    venue_id: int
    name: str
    status: Optional[str] = CourtStatus.ACTIVE.value
    price: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# OperatingHour Schemas
class OperatingHourBase(BaseModel):
    day_of_week: int = Field(ge=0, le=6)  # 0 = Thứ Hai ... 6 = Chủ Nhật
    open_time: time
    close_time: time

    @model_validator(mode="after")
    def _open_before_close(self):
        if self.open_time >= self.close_time:
            raise ValueError("Giờ mở cửa phải trước giờ đóng cửa.")
        return self


class OperatingHourCreate(OperatingHourBase):
    pass


class OperatingHoursUpdate(BaseModel):
    """Thay toàn bộ lịch hoạt động trong tuần; ngày không có trong danh sách là ngày nghỉ."""
    hours: List[OperatingHourBase]

    @model_validator(mode="after")
    def _unique_days(self):
        days = [h.day_of_week for h in self.hours]
        if len(days) != len(set(days)):
            raise ValueError("Mỗi ngày trong tuần chỉ được khai báo một khung giờ.")
        return self


class OperatingHourResponse(BaseModel):
    id: int
    venue_id: int
    day_of_week: int
    open_time: time
    close_time: time

    model_config = ConfigDict(from_attributes=True)


# PriceRule Schemas
class PriceRuleBase(BaseModel):
    rule_type: str = PriceRuleType.BASE.value
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    price: float = Field(gt=0)


class PriceRuleCreate(PriceRuleBase):
    pass


class PriceRuleResponse(BaseModel):
    id: int
    venue_id: int
    rule_type: Optional[str] = PriceRuleType.BASE.value
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    price: float

    model_config = ConfigDict(from_attributes=True)


class VenuePricingUpdate(BaseModel):
    base_price: float = Field(gt=0, le=100_000_000)
    peak_price: Optional[float] = Field(default=None, gt=0, le=100_000_000)
    weekend_price: Optional[float] = Field(default=None, ge=0, le=100_000_000)
    # Khung giờ cao điểm; bỏ trống thì giữ khung hiện tại (mặc định 17:00 - 23:00)
    peak_start: Optional[time] = None
    peak_end: Optional[time] = None

    @model_validator(mode="after")
    def _peak_window(self):
        if self.peak_start and self.peak_end and self.peak_start >= self.peak_end:
            raise ValueError("Giờ bắt đầu cao điểm phải trước giờ kết thúc.")
        return self


class AmenityResponse(BaseModel):
    id: int
    name: str
    icon: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Venue Schemas
class VenueBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: Optional[str] = None
    address: str = Field(min_length=1, max_length=255)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[str] = None
    status: str = VenueStatus.ACTIVE.value


class VenueCreate(VenueBase):
    model_config = ConfigDict(extra="ignore")


class VenueUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    address: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[Union[List[str], str]] = None
    amenity_ids: Optional[List[int]] = None
    # Thông tin nhận tiền của chủ cụm sân
    bank_account: Optional[str] = Field(default=None, max_length=160)
    company_name: Optional[str] = Field(default=None, max_length=160)
    # Đơn tại quầy chưa thu tiền tự hủy khi còn bấy nhiêu phút tới giờ chơi (0 = không tự hủy, tối đa 24 giờ)
    unpaid_desk_release_minutes: Optional[int] = Field(default=None, ge=0, le=1440)

    model_config = ConfigDict(extra="ignore")


class UpcomingBookingResponse(BaseModel):
    """Một đơn còn hiệu lực sắp diễn ra trên một sân: cần xử lý trước khi tạm ngưng sân hay cụm sân."""
    booking_id: int
    booking_code: Optional[str] = None
    status: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    court_id: int
    court_name: Optional[str] = None
    date: date
    start_time: time
    end_time: time


class VenueStatusUpdate(BaseModel):
    status: VenueStatus


class AdminVenueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    owner_id: int
    status: VenueStatus = VenueStatus.ACTIVE
    courts_count: int = Field(default=2, ge=1, le=20)
    base_price: float = Field(default=150000, gt=0)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    model_config = ConfigDict(extra="ignore")


class AdminVenueUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    address: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[VenueStatus] = None
    owner_id: Optional[int] = None
    image_url: Optional[str] = None
    images: Optional[Union[List[str], str]] = None

    model_config = ConfigDict(extra="ignore")


class AssignOwnerRequest(BaseModel):
    owner_id: int


class ReviewCreate(BaseModel):
    rating: float = Field(ge=1, le=5)
    comment: Optional[str] = Field(default=None, max_length=1000)


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    rating: float
    comment: Optional[str] = None
    created_at: Optional[datetime] = None
    author_name: str


class VenueResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    description: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    google_maps_url: Optional[str] = None
    image_url: Optional[str] = None
    images: Optional[str] = None
    status: Optional[str] = VenueStatus.ACTIVE.value
    unpaid_desk_release_minutes: int = 30
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    courts: List[CourtResponse] = []
    operating_hours: List[OperatingHourResponse] = []
    price_rules: List[PriceRuleResponse] = []
    amenities: List[AmenityResponse] = []

    model_config = ConfigDict(from_attributes=True)


class VenueManageResponse(VenueResponse):
    """Thông tin cụm sân dành cho người quản lý (kèm thông tin nhận tiền của chủ sân)."""
    owner_full_name: Optional[str] = None
    owner_company_name: Optional[str] = None
    owner_bank_account: Optional[str] = None
