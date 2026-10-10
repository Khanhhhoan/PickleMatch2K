from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.venue import VenueResponse


class VenueSearchResult(VenueResponse):
    distance_km: Optional[float] = None


class TimeSlot(BaseModel):
    start_time: time
    end_time: time
    price: float
    is_available: bool
    is_past: bool = False       # Khung giờ đã trôi qua
    is_held: bool = False       # Đang được người khác giữ tạm
    held_by_me: bool = False    # Đang được chính người xem giữ tạm
    held_by_user: Optional[str] = None  # Giữ lại để tương thích; không còn trả tên người giữ
    hold_seconds_remaining: Optional[int] = None


class CourtAvailability(BaseModel):
    court_id: int
    court_name: str
    slots: List[TimeSlot]


class VenueAvailabilityResponse(BaseModel):
    venue_id: int
    date: date
    courts: List[CourtAvailability]
