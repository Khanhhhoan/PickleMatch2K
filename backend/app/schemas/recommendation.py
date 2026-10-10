from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.venue import VenueResponse


class VenueRecommendationResponse(BaseModel):
    venue: VenueResponse
    score: float  # Điểm tổng hợp 0..1
    # Điểm thành phần 0..1; None = tiêu chí không có dữ liệu nên không được tính
    distance_score: Optional[float] = None
    price_score: Optional[float] = None
    time_score: float
    rating_score: float
    preference_score: Optional[float] = None
    criteria_used: List[str] = []
    distance_km: Optional[float] = None
    avg_price: Optional[float] = None      # Giá trung bình mỗi giờ của các khung còn trống trong ngày
    avg_rating: Optional[float] = None     # Điểm đánh giá (trung bình Bayes, thang 5)
    review_count: int = 0
    free_slots: int = 0
    total_slots: int = 0

    model_config = ConfigDict(from_attributes=True)
