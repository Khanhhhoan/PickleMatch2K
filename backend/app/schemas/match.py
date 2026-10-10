from datetime import date, datetime, time
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.match import MatchStatus

Purpose = Literal["recreational", "practice", "competitive"]


class MatchParticipantResponse(BaseModel):
    id: int
    user_id: int
    status: str
    joined_at: Optional[datetime] = None
    user_name: Optional[str] = None
    skill_level: Optional[float] = None
    play_style: Optional[str] = None
    # Số điện thoại chỉ trả về cho thành viên của chính phòng đấu đó
    phone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MatchCreate(BaseModel):
    """Người chơi mở phòng đấu trên một đơn đặt sân đã thanh toán cọc; sân và giờ lấy từ đơn đó."""
    booking_id: int
    required_skill: Optional[float] = Field(default=None, ge=1.0, le=8.0)
    num_players: int = Field(default=4, ge=2, le=8)
    purpose: Optional[Purpose] = "recreational"
    notes: Optional[str] = Field(default=None, max_length=300)

    model_config = ConfigDict(extra="ignore")


class MatchAdminCreate(BaseModel):
    venue_id: int
    court_id: Optional[int] = None
    booking_id: Optional[int] = None
    date: date
    start_time: time
    end_time: time
    required_skill: Optional[float] = Field(default=None, ge=1.0, le=8.0)
    num_players: int = Field(default=4, ge=2, le=8)
    purpose: Optional[Purpose] = "recreational"
    notes: Optional[str] = Field(default=None, max_length=300)
    creator_id: Optional[int] = None
    status: MatchStatus = MatchStatus.OPEN

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def _time_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("Giờ kết thúc phải sau giờ bắt đầu.")
        return self


class MatchAdminUpdate(BaseModel):
    venue_id: Optional[int] = None
    court_id: Optional[int] = None
    date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    required_skill: Optional[float] = Field(default=None, ge=1.0, le=8.0)
    num_players: Optional[int] = Field(default=None, ge=2, le=8)
    purpose: Optional[Purpose] = None
    status: Optional[MatchStatus] = None
    notes: Optional[str] = Field(default=None, max_length=300)

    model_config = ConfigDict(extra="ignore")


class MatchStatusUpdate(BaseModel):
    status: MatchStatus


class AddParticipantRequest(BaseModel):
    user_id: int


class MatchResponse(BaseModel):
    id: int
    creator_id: int
    venue_id: int
    court_id: Optional[int] = None
    booking_id: Optional[int] = None
    booking_code: Optional[str] = None
    date: date
    start_time: time
    end_time: time
    required_skill: Optional[float] = None
    num_players: int
    purpose: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    court_name: Optional[str] = None
    venue_name: Optional[str] = None
    creator_name: Optional[str] = None
    creator_skill_level: Optional[float] = None
    creator_play_style: Optional[str] = None
    participants: List[MatchParticipantResponse] = []
    # Độ phù hợp do mô hình ghép cặp ước lượng (0-100); None khi chưa có mô hình hoặc chưa đăng nhập
    compatibility: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
