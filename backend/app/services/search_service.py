from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models.venue import Venue, VenueStatus
from app.schemas.search import VenueSearchResult
from app.utils.geo import haversine_distance


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_venues(
    db: Session,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: Optional[float] = None,
    keyword: Optional[str] = None,
) -> List[VenueSearchResult]:
    """Cụm sân đang hoạt động, lọc theo từ khóa/bán kính và sắp theo khoảng cách khi biết vị trí."""
    query = (
        db.query(Venue)
        .options(
            selectinload(Venue.courts), selectinload(Venue.operating_hours),
            selectinload(Venue.price_rules), selectinload(Venue.amenities),
        )
        .filter(Venue.status == VenueStatus.ACTIVE.value)
    )

    keyword = (keyword or "").strip()
    if keyword:
        pattern = f"%{_escape_like(keyword)}%"
        query = query.filter(or_(Venue.name.ilike(pattern, escape="\\"), Venue.address.ilike(pattern, escape="\\")))

    has_origin = latitude is not None and longitude is not None
    results = []
    for venue in query.order_by(Venue.id).all():
        dist = None
        if has_origin and venue.latitude is not None and venue.longitude is not None:
            dist = haversine_distance(latitude, longitude, venue.latitude, venue.longitude)
        if radius_km is not None and has_origin and (dist is None or dist > radius_km):
            continue

        result = VenueSearchResult.model_validate(venue)
        result.distance_km = round(dist, 2) if dist is not None else None
        results.append(result)

    if has_origin:
        results.sort(key=lambda r: r.distance_km if r.distance_km is not None else float("inf"))
    return results
