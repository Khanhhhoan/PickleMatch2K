from datetime import date, time
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.recommendation import VenueRecommendationResponse
from app.services import venue_recommendation_service

router = APIRouter()


@router.get("/venues", response_model=List[VenueRecommendationResponse])
def recommend_venues(
    latitude: Optional[float] = Query(None, ge=-90, le=90, description="Vĩ độ người dùng"),
    longitude: Optional[float] = Query(None, ge=-180, le=180, description="Kinh độ người dùng"),
    target_date: Optional[date] = Query(None, description="Ngày muốn chơi (mặc định hôm nay)"),
    radius_km: Optional[float] = Query(None, gt=0, le=200, description="Chỉ xét sân trong bán kính này"),
    budget_max: Optional[float] = Query(None, gt=0, description="Ngân sách tối đa mỗi giờ (VNĐ)"),
    amenity_ids: Optional[List[int]] = Query(None, description="Tiện ích mong muốn"),
    time_from: Optional[time] = Query(None, description="Giờ sớm nhất muốn chơi"),
    time_to: Optional[time] = Query(None, description="Giờ muộn nhất muốn chơi"),
    top_n: int = Query(6, ge=1, le=20),
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_user_optional),
):
    """
    Top-N cụm sân phù hợp theo điểm đa tiêu chí:
    Score = (0.30·D + 0.25·P + 0.20·T + 0.15·R + 0.10·S) / tổng trọng số các tiêu chí có dữ liệu.
    Tham số không truyền (vị trí, ngân sách, tiện ích) được lấy từ hồ sơ người chơi nếu đã đăng nhập.
    """
    return venue_recommendation_service.get_venue_recommendations(
        db=db,
        user_profile=current_user.player_profile if current_user else None,
        latitude=latitude,
        longitude=longitude,
        target_date=target_date,
        radius_km=radius_km,
        budget_max=budget_max,
        preferred_amenity_ids=amenity_ids,
        time_from=time_from,
        time_to=time_to,
        top_n=top_n,
    )
