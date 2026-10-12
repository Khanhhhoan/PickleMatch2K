"""
Gợi ý cụm sân theo phương pháp lọc -> chấm điểm đa tiêu chí -> xếp hạng (xem recommendation_config).

    Score = Σ w_i * s_i / Σ w_i     (chỉ trên các tiêu chí có dữ liệu)

    D  Khoảng cách từ người dùng tới sân
    P  Mức giá so với ngân sách (hoặc so với các sân ứng viên khi yêu cầu không kèm ngân sách)
    T  Tỷ lệ khung giờ còn trống trong ngày/khoảng giờ muốn chơi
    R  Điểm đánh giá (trung bình Bayes)
    S  Mức đáp ứng các tiện ích người dùng yêu cầu

Vị trí lấy từ yêu cầu, không có thì lấy từ hồ sơ người chơi. Ngân sách và tiện ích chỉ lấy từ yêu cầu.
"""
from datetime import date, time
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.recommendation_config import (
    BUDGET_OVERRUN_LIMIT,
    MAX_EXPECTED_DISTANCE_KM,
    MAX_RATING,
    RATING_PRIOR_FALLBACK,
    RATING_PRIOR_WEIGHT,
    WEIGHTS,
)
from app.models.user import PlayerProfile
from app.models.venue import Review, Venue, VenueStatus
from app.schemas.recommendation import VenueRecommendationResponse
from app.schemas.venue import VenueResponse
from app.services.availability_service import get_venue_availability
from app.utils.geo import haversine_distance
from app.utils.timeutils import today_vn


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize_distance(dist_km: Optional[float]) -> Optional[float]:
    """Càng gần càng tốt. None khi chưa biết vị trí (tiêu chí bị loại khỏi phép tính)."""
    if dist_km is None:
        return None
    return _clamp(1.0 - dist_km / MAX_EXPECTED_DISTANCE_KM)


def normalize_price(price: float, *, budget: Optional[float] = None,
                    min_price: Optional[float] = None, max_price: Optional[float] = None) -> float:
    """
    Có ngân sách: 1 điểm khi giá <= ngân sách, giảm tuyến tính về 0 khi vượt 50% ngân sách.
    Không có ngân sách: min-max trên tập ứng viên (rẻ nhất = 1, đắt nhất = 0; bằng nhau = 1).
    """
    if budget and budget > 0:
        if price <= budget:
            return 1.0
        return _clamp(1.0 - (price - budget) / (budget * BUDGET_OVERRUN_LIMIT))
    if min_price is None or max_price is None or max_price <= min_price:
        return 1.0
    return _clamp((max_price - price) / (max_price - min_price))


def normalize_time(available_slots: int, total_slots: int) -> float:
    """Tỷ lệ khung giờ còn trống; 0 khi sân nghỉ hoặc không còn khung nào đặt được."""
    if total_slots <= 0:
        return 0.0
    return _clamp(available_slots / total_slots)


def bayesian_rating(review_count: int, mean_rating: Optional[float], prior_mean: float) -> float:
    """Trung bình Bayes trên thang 5: sân chưa có đánh giá nhận đúng điểm trung bình toàn hệ thống."""
    if review_count <= 0 or mean_rating is None:
        return prior_mean
    return (review_count * mean_rating + RATING_PRIOR_WEIGHT * prior_mean) / (review_count + RATING_PRIOR_WEIGHT)


def normalize_rating(rating: float) -> float:
    return _clamp(rating / MAX_RATING)


def normalize_preference(venue_amenity_ids: set, preferred_ids: set) -> Optional[float]:
    """Tỷ lệ tiện ích được yêu cầu mà sân đáp ứng. None khi yêu cầu không nêu tiện ích nào."""
    if not preferred_ids:
        return None
    return len(venue_amenity_ids & preferred_ids) / len(preferred_ids)


def weighted_score(scores: Dict[str, Optional[float]]) -> float:
    used = {name: value for name, value in scores.items() if value is not None}
    total_weight = sum(WEIGHTS[name] for name in used)
    if total_weight <= 0:
        return 0.0
    return sum(WEIGHTS[name] * value for name, value in used.items()) / total_weight


def get_venue_recommendations(
    db: Session,
    user_profile: Optional[PlayerProfile] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    target_date: Optional[date] = None,
    radius_km: Optional[float] = None,
    budget_max: Optional[float] = None,
    preferred_amenity_ids: Optional[Sequence[int]] = None,
    time_from: Optional[time] = None,
    time_to: Optional[time] = None,
    top_n: int = 10,
) -> List[VenueRecommendationResponse]:
    ref_lat = latitude if latitude is not None else (user_profile.latitude if user_profile else None)
    ref_lng = longitude if longitude is not None else (user_profile.longitude if user_profile else None)
    eval_date = target_date or today_vn()
    budget = budget_max or None
    preferred = set(preferred_amenity_ids or [])

    venues = (
        db.query(Venue)
        .options(
            selectinload(Venue.courts), selectinload(Venue.price_rules),
            selectinload(Venue.amenities), selectinload(Venue.operating_hours),
        )
        .filter(Venue.status == VenueStatus.ACTIVE.value)
        .all()
    )

    review_stats = {
        venue_id: (count, mean)
        for venue_id, count, mean in db.query(Review.venue_id, func.count(Review.id), func.avg(Review.rating))
        .group_by(Review.venue_id).all()
    }
    # Điểm trung bình toàn hệ thống cũng được kéo về mốc mặc định khi tổng số đánh giá còn ít,
    # để một vài đánh giá đầu tiên không quyết định điểm của mọi sân chưa có đánh giá.
    total_reviews = sum(int(count) for count, _ in review_stats.values())
    global_mean = db.query(func.avg(Review.rating)).scalar()
    prior_mean = bayesian_rating(
        total_reviews, float(global_mean) if global_mean is not None else None, RATING_PRIOR_FALLBACK
    )

    # Bước 1 - lọc và thu thập dữ liệu thô của từng sân
    candidates = []
    for venue in venues:
        dist_km = None
        if None not in (ref_lat, ref_lng, venue.latitude, venue.longitude):
            dist_km = haversine_distance(ref_lat, ref_lng, venue.latitude, venue.longitude)
        if radius_km is not None and dist_km is not None and dist_km > radius_km:
            continue

        availability = get_venue_availability(db, venue.id, eval_date)
        slots = [
            slot
            for court in (availability.courts if availability else [])
            for slot in court.slots
            if not slot.is_past
            and (time_from is None or slot.start_time >= time_from)
            and (time_to is None or slot.end_time <= time_to)
        ]
        free_slots = [s for s in slots if s.is_available and not s.is_held]
        priced = free_slots or slots
        ref_price = sum(s.price for s in priced) / len(priced) if priced else None
        if ref_price is None and venue.price_rules:
            ref_price = sum(r.price for r in venue.price_rules) / len(venue.price_rules)

        count, mean = review_stats.get(venue.id, (0, None))
        candidates.append({
            "venue": venue,
            "dist_km": dist_km,
            "price": ref_price,
            "free": len(free_slots),
            "total": len(slots),
            "review_count": int(count),
            "rating": bayesian_rating(int(count), float(mean) if mean is not None else None, prior_mean),
        })

    # Bước 2 - chuẩn hóa về [0, 1] và tính điểm tổng hợp
    prices = [c["price"] for c in candidates if c["price"] is not None]
    min_price, max_price = (min(prices), max(prices)) if prices else (None, None)

    recommendations = []
    for c in candidates:
        venue = c["venue"]
        scores = {
            "distance": normalize_distance(c["dist_km"]),
            "price": normalize_price(c["price"], budget=budget, min_price=min_price, max_price=max_price)
            if c["price"] is not None else None,
            "time": normalize_time(c["free"], c["total"]),
            "rating": normalize_rating(c["rating"]),
            "preference": normalize_preference({a.id for a in venue.amenities}, preferred),
        }
        recommendations.append(VenueRecommendationResponse(
            venue=VenueResponse.model_validate(venue),
            score=round(weighted_score(scores), 4),
            distance_score=round(scores["distance"], 3) if scores["distance"] is not None else None,
            price_score=round(scores["price"], 3) if scores["price"] is not None else None,
            time_score=round(scores["time"], 3),
            rating_score=round(scores["rating"], 3),
            preference_score=round(scores["preference"], 3) if scores["preference"] is not None else None,
            distance_km=round(c["dist_km"], 1) if c["dist_km"] is not None else None,
            avg_price=round(c["price"]) if c["price"] is not None else None,
            avg_rating=round(c["rating"], 2),
            review_count=c["review_count"],
            free_slots=c["free"],
            total_slots=c["total"],
            criteria_used=[name for name, value in scores.items() if value is not None],
        ))

    # Bước 3 - xếp hạng Top-N
    recommendations.sort(key=lambda r: r.score, reverse=True)
    return recommendations[:top_n]
