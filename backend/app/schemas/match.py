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
    # Số đầy đủ chỉ trả về giữa các thành viên đã được duyệt; người khác nhận số đã che (0901***233)
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
    # Số thành viên đã được duyệt (gồm chủ phòng): con số "đã có / cần" của phòng
    accepted_count: int = 0
    # Trạng thái của chính người xem trong phòng: None, PENDING, ACCEPTED, REJECTED
    my_status: Optional[str] = None
    # Số yêu cầu chờ duyệt; chỉ chủ phòng nhận được con số này
    pending_count: int = 0
    # Độ phù hợp do mô hình ghép cặp ước lượng (0-100); None khi chưa có mô hình hoặc chưa đăng nhập
    compatibility: Optional[float] = None
    # True khi độ phù hợp đạt ngưỡng đề xuất (app/core/matching_policy.py)
    is_recommended: bool = False

    model_config = ConfigDict(from_attributes=True)
