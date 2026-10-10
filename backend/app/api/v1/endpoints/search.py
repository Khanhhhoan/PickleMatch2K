from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User
from app.schemas.search import VenueAvailabilityResponse, VenueSearchResult
from app.services import availability_service, search_service

router = APIRouter()


@router.get("/venues", response_model=List[VenueSearchResult])
def search_venues(
    db: Session = Depends(deps.get_db),
    latitude: Optional[float] = Query(None, ge=-90, le=90, description="Vĩ độ người dùng"),
    longitude: Optional[float] = Query(None, ge=-180, le=180, description="Kinh độ người dùng"),
    radius_km: Optional[float] = Query(None, gt=0, le=500, description="Bán kính tìm kiếm (km)"),
    keyword: Optional[str] = Query(None, max_length=100, description="Từ khóa theo tên hoặc địa chỉ"),
):
    """Tìm cụm sân theo từ khóa và vị trí."""
    return search_service.search_venues(
        db=db, latitude=latitude, longitude=longitude, radius_km=radius_km, keyword=keyword
    )


@router.get("/venues/{venue_id}/availability", response_model=VenueAvailabilityResponse)
def get_venue_availability(
    venue_id: int,
    target_date: date = Query(..., description="Ngày cần xem lịch (YYYY-MM-DD)"),
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_user_optional),
):
    """Lịch trống và giá từng khung giờ của một cụm sân trong ngày."""
    result = availability_service.get_venue_availability(
        db, venue_id, target_date, viewer_id=current_user.id if current_user else None
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cụm sân")
    return result
