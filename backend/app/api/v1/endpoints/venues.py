import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api import deps
from app.api.permissions import can_manage_venue, get_venue_or_404, managed_venue_ids, require_venue_owner
from app.models.user import OwnerProfile, User, UserRole
from app.models.venue import Amenity, Court, PriceRule, Review, Venue, VenueStatus
from app.schemas.venue import (
    AdminVenueCreate,
    AdminVenueUpdate,
    AmenityResponse,
    AssignOwnerRequest,
    CourtCreate,
    CourtResponse,
    CourtUpdate,
    OperatingHourCreate,
    OperatingHourResponse,
    OperatingHoursUpdate,
    PriceRuleCreate,
    PriceRuleResponse,
    ReviewCreate,
    ReviewResponse,
    VenueCreate,
    VenueManageResponse,
    VenuePricingUpdate,
    VenueResponse,
    VenueStatusUpdate,
    VenueUpdate,
)
from app.services import storage_service, venue_service

router = APIRouter()

owner_or_admin = deps.RoleChecker([UserRole.OWNER.value, UserRole.ADMIN.value])
admin_only = deps.RoleChecker([UserRole.ADMIN.value])
venue_staff_roles = deps.RoleChecker([UserRole.OWNER.value, UserRole.ADMIN.value, UserRole.STAFF.value])


def _load_images(venue: Venue) -> List[str]:
    if not venue.images:
        return []
    try:
        images = json.loads(venue.images)
        return [str(i) for i in images] if isinstance(images, list) else []
    except (TypeError, ValueError):
        return []


def _set_images(venue: Venue, images) -> None:
    if isinstance(images, list):
        venue.images = json.dumps(images) if images else None
    else:
        venue.images = images or None


def _manage_view(venue: Venue, viewer: User) -> VenueManageResponse:
    data = VenueResponse.model_validate(venue).model_dump()
    profile = venue.owner.owner_profile if venue.owner else None
    show_payout = viewer.role != UserRole.STAFF.value and profile is not None
    return VenueManageResponse(
        **data,
        owner_full_name=profile.full_name if profile else None,
        owner_company_name=profile.company_name if show_payout else None,
        owner_bank_account=profile.bank_account if show_payout else None,
    )


# ==========================================
# PUBLIC
# ==========================================

@router.get("", response_model=List[VenueResponse])
def list_venues(
    db: Session = Depends(deps.get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    """Danh sách cụm sân đang hoạt động (công khai)."""
    return (
        db.query(Venue)
        .filter(Venue.status == VenueStatus.ACTIVE.value)
        .order_by(Venue.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/amenities", response_model=List[AmenityResponse])
def list_amenities(db: Session = Depends(deps.get_db)):
    """Danh mục tiện ích sân (công khai)."""
    return db.query(Amenity).order_by(Amenity.id.asc()).all()


@router.get("/me", response_model=List[VenueManageResponse])
def read_my_venues(db: Session = Depends(deps.get_db), current_user: User = Depends(venue_staff_roles)):
    """Các cụm sân mà người dùng đang quản lý (chủ sân) hoặc được phân công (nhân viên)."""
    query = db.query(Venue)
    venue_ids = managed_venue_ids(db, current_user)
    if venue_ids is not None:
        if not venue_ids:
            return []
        query = query.filter(Venue.id.in_(venue_ids))
    return [_manage_view(v, current_user) for v in query.order_by(Venue.id.asc()).all()]


@router.post("", response_model=VenueResponse)
def create_venue(
    venue_in: VenueCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Chủ sân tự tạo cụm sân của mình (mỗi chủ sân một cụm). Admin dùng POST /venues/admin."""
    return venue_service.create_venue(db=db, venue_in=venue_in, owner_id=current_user.id)


# ==========================================
# ADMIN (đặt trước các route /{venue_id})
# ==========================================

@router.get("/admin/all", response_model=List[VenueManageResponse])
def get_all_venues_admin(db: Session = Depends(deps.get_db), current_user: User = Depends(admin_only)):
    """Toàn bộ cụm sân ở mọi trạng thái, kèm thông tin chủ sân."""
    return [_manage_view(v, current_user) for v in db.query(Venue).order_by(Venue.id.asc()).all()]


@router.post("/admin", response_model=VenueResponse)
def admin_create_venue(
    payload: AdminVenueCreate,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    """Admin tạo cụm sân cho một chủ sân, kèm sân con và giá cơ bản."""
    owner = db.query(User).filter(User.id == payload.owner_id, User.role == UserRole.OWNER.value).first()
    if not owner:
        raise HTTPException(status_code=400, detail="Tài khoản chỉ định không phải là Chủ sân (OWNER) hợp lệ")

    venue = Venue(
        name=payload.name,
        address=payload.address,
        description=payload.description,
        owner_id=owner.id,
        status=payload.status.value,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(venue)
    db.flush()
    for i in range(1, payload.courts_count + 1):
        db.add(Court(name=f"Sân {i}", venue_id=venue.id, status="ACTIVE"))
    db.add(PriceRule(venue_id=venue.id, rule_type="BASE", price=payload.base_price))
    db.commit()
    db.refresh(venue)
    return venue


@router.put("/admin/{venue_id}", response_model=VenueResponse)
def admin_update_venue(
    venue_id: int,
    payload: AdminVenueUpdate,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    venue = get_venue_or_404(db, venue_id)
    changes = payload.model_dump(exclude_unset=True)

    for field in ("name", "address"):
        if changes.get(field):
            setattr(venue, field, changes[field])
    if "description" in changes:
        venue.description = changes["description"]
    if changes.get("status") is not None:
        venue.status = changes["status"].value
    if changes.get("owner_id"):
        owner = db.query(User).filter(User.id == changes["owner_id"], User.role == UserRole.OWNER.value).first()
        if not owner:
            raise HTTPException(status_code=400, detail="Tài khoản chỉ định không phải là Chủ sân (OWNER) hợp lệ")
        venue.owner_id = owner.id
    if "image_url" in changes:
        venue.image_url = changes["image_url"]
    if "images" in changes:
        _set_images(venue, changes["images"])

    db.commit()
    db.refresh(venue)
    return venue


@router.delete("/admin/{venue_id}")
def admin_delete_venue(
    venue_id: int,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    """
    Chỉ xóa được cụm sân chưa phát sinh đơn đặt hoặc phòng đấu. Cụm sân đã có lịch sử phải
    chuyển sang trạng thái Ngừng hoạt động để giữ dữ liệu thống kê và truy vết.
    """
    from app.models.booking import BookingDetail
    from app.models.match import Match
    from app.models.user import StaffProfile

    venue = get_venue_or_404(db, venue_id)
    court_ids = [c.id for c in venue.courts]
    has_bookings = bool(court_ids) and (
        db.query(BookingDetail.id).filter(BookingDetail.court_id.in_(court_ids)).first() is not None
    )
    has_matches = db.query(Match.id).filter(Match.venue_id == venue_id).first() is not None
    if has_bookings or has_matches:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cụm sân đã có lịch sử đặt sân/phòng đấu nên không thể xóa. Hãy chuyển sang trạng thái Ngừng hoạt động.",
        )

    db.query(StaffProfile).filter(StaffProfile.venue_id == venue_id).update({"venue_id": None})
    venue.amenities = []
    db.delete(venue)
    db.commit()
    return {"status": "success", "message": f"Đã xóa cụm sân #{venue_id} thành công"}


@router.put("/admin/{venue_id}/assign-owner", response_model=VenueResponse)
def assign_venue_owner(
    venue_id: int,
    payload: AssignOwnerRequest,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    venue = get_venue_or_404(db, venue_id)
    owner = db.query(User).filter(User.id == payload.owner_id, User.role == UserRole.OWNER.value).first()
    if not owner:
        raise HTTPException(status_code=400, detail="Tài khoản chỉ định không phải là Chủ sân (OWNER) hợp lệ")
    venue.owner_id = owner.id
    db.commit()
    db.refresh(venue)
    return venue


# ==========================================
# VENUE DETAIL & CONFIGURATION
# ==========================================

@router.get("/{venue_id}", response_model=VenueResponse)
def read_venue(
    venue_id: int,
    db: Session = Depends(deps.get_db),
    current_user: Optional[User] = Depends(deps.get_current_user_optional),
):
    """Chi tiết cụm sân. Cụm sân chưa hoạt động chỉ người quản lý mới xem được."""
    venue = get_venue_or_404(db, venue_id)
    if venue.status != VenueStatus.ACTIVE.value:
        if not current_user or not can_manage_venue(current_user, venue, allow_staff=True):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cụm sân")
    return venue


@router.put("/{venue_id}", response_model=VenueResponse)
def update_venue(
    venue_id: int,
    payload: VenueUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Cập nhật thông tin cụm sân và tài khoản nhận tiền. Chỉ chủ của cụm sân hoặc Admin."""
    venue = require_venue_owner(db, current_user, venue_id)
    changes = payload.model_dump(exclude_unset=True)

    for field in ("name", "address"):
        if changes.get(field):
            setattr(venue, field, changes[field].strip())
    for field in ("description", "image_url"):
        if field in changes:
            setattr(venue, field, changes[field])
    for field in ("latitude", "longitude"):
        if changes.get(field) is not None:
            setattr(venue, field, changes[field])
    if "images" in changes:
        _set_images(venue, changes["images"])
    if changes.get("google_maps_url"):
        venue.google_maps_url = changes["google_maps_url"]
    elif not venue.google_maps_url and venue.latitude and venue.longitude:
        venue.google_maps_url = f"https://www.google.com/maps/search/?api=1&query={venue.latitude},{venue.longitude}"
    if changes.get("amenity_ids") is not None:
        venue.amenities = db.query(Amenity).filter(Amenity.id.in_(changes["amenity_ids"])).all()

    if "bank_account" in changes or "company_name" in changes:
        profile = venue.owner.owner_profile if venue.owner else None
        if profile is None and venue.owner is not None:
            profile = OwnerProfile(user_id=venue.owner.id)
            venue.owner.owner_profile = profile
        if profile is not None:
            if changes.get("bank_account"):
                profile.bank_account = changes["bank_account"].strip()
            if changes.get("company_name"):
                profile.company_name = changes["company_name"].strip()

    db.commit()
    db.refresh(venue)
    return venue


@router.put("/{venue_id}/status", response_model=VenueResponse)
def update_venue_status(
    venue_id: int,
    payload: VenueStatusUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """
    Đổi trạng thái cụm sân. Chủ sân chỉ chuyển qua lại giữa ACTIVE, MAINTENANCE, INACTIVE;
    việc duyệt (PENDING -> ACTIVE) hay từ chối (REJECTED) là quyền của Admin.
    """
    venue = require_venue_owner(db, current_user, venue_id)
    if current_user.role != UserRole.ADMIN.value:
        owner_statuses = {VenueStatus.ACTIVE, VenueStatus.MAINTENANCE, VenueStatus.INACTIVE}
        awaiting_admin = venue.status in (VenueStatus.PENDING.value, VenueStatus.REJECTED.value)
        if payload.status not in owner_statuses or awaiting_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cụm sân đang chờ duyệt hoặc đã bị từ chối: chỉ Admin mới thay đổi được trạng thái này.",
            )
    venue.status = payload.status.value
    db.commit()
    db.refresh(venue)
    return venue


@router.post("/{venue_id}/upload-image")
async def upload_venue_image(
    venue_id: int,
    file: UploadFile = File(...),
    is_primary: bool = Form(True),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Tải ảnh cho cụm sân (ảnh bìa hoặc thư viện). Định dạng được xác định từ nội dung file."""
    venue = require_venue_owner(db, current_user, venue_id)

    limit = storage_service.max_image_bytes()
    contents = await file.read(limit + 1)
    if len(contents) > limit:
        raise HTTPException(status_code=400, detail="Dung lượng ảnh vượt quá giới hạn cho phép.")
    stored_url = await run_in_threadpool(storage_service.save_venue_image, venue_id, contents)

    images = _load_images(venue)
    if stored_url not in images:
        images.append(stored_url)
    _set_images(venue, images)
    if is_primary or not venue.image_url:
        venue.image_url = stored_url
    db.commit()
    db.refresh(venue)

    return {
        "status": "success",
        "message": "Tải ảnh lên thành công",
        "image_url": venue.image_url,
        "images": images,
        "uploaded_file": stored_url,
    }


@router.delete("/{venue_id}/images")
def delete_venue_image(
    venue_id: int,
    image_url: str = Query(..., description="Đường dẫn ảnh cần xóa"),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Xóa một ảnh khỏi cụm sân. Chỉ xóa được ảnh đang thuộc chính cụm sân này."""
    venue = require_venue_owner(db, current_user, venue_id)
    images = _load_images(venue)
    if image_url not in images and venue.image_url != image_url:
        raise HTTPException(status_code=404, detail="Ảnh không thuộc cụm sân này")

    images = [i for i in images if i != image_url]
    _set_images(venue, images)
    if venue.image_url == image_url:
        venue.image_url = images[0] if images else None
    db.commit()
    db.refresh(venue)

    storage_service.delete_venue_image_file(image_url)
    return {"status": "success", "message": "Đã xóa ảnh thành công", "image_url": venue.image_url, "images": images}


@router.post("/{venue_id}/courts", response_model=CourtResponse)
def create_court(
    venue_id: int,
    court_in: CourtCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    venue = require_venue_owner(db, current_user, venue_id)
    return venue_service.create_court(db, venue, court_in)


@router.put("/{venue_id}/courts/{court_id}", response_model=CourtResponse)
def update_court(
    venue_id: int,
    court_id: int,
    court_in: CourtUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Đổi tên, trạng thái (ACTIVE/MAINTENANCE) hoặc giá riêng của một sân."""
    venue = require_venue_owner(db, current_user, venue_id)
    return venue_service.update_court(db, venue, court_id, court_in)


@router.delete("/{venue_id}/courts/{court_id}")
def delete_court(
    venue_id: int,
    court_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    venue = require_venue_owner(db, current_user, venue_id)
    venue_service.delete_court(db, venue, court_id)
    return {"status": "success", "message": "Đã xóa sân"}


@router.post("/{venue_id}/operating-hours", response_model=OperatingHourResponse)
def upsert_operating_hour(
    venue_id: int,
    oh_in: OperatingHourCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Đặt giờ mở cửa cho một ngày trong tuần (ghi đè nếu ngày đó đã có)."""
    venue = require_venue_owner(db, current_user, venue_id)
    return venue_service.upsert_operating_hour(db, venue, oh_in)


@router.put("/{venue_id}/operating-hours", response_model=List[OperatingHourResponse])
def replace_operating_hours(
    venue_id: int,
    payload: OperatingHoursUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Thay toàn bộ lịch hoạt động trong tuần; ngày không gửi lên là ngày nghỉ."""
    venue = require_venue_owner(db, current_user, venue_id)
    return venue_service.replace_operating_hours(db, venue, payload.hours)


@router.post("/{venue_id}/price-rules", response_model=PriceRuleResponse)
def create_price_rule(
    venue_id: int,
    rule_in: PriceRuleCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    venue = require_venue_owner(db, current_user, venue_id)
    return venue_service.upsert_price_rule(db, venue, rule_in)


@router.post("/{venue_id}/pricing")
@router.put("/{venue_id}/pricing")
def update_venue_pricing_endpoint(
    venue_id: int,
    payload: VenuePricingUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Cập nhật đồng bộ giá giờ thường, giờ cao điểm và cuối tuần của cụm sân."""
    venue = require_venue_owner(db, current_user, venue_id)
    return venue_service.update_venue_pricing(
        db, venue, payload.base_price, payload.peak_price, payload.weekend_price, payload.peak_start, payload.peak_end
    )


# ==========================================
# REVIEWS
# ==========================================

def _review_author(review: Review) -> str:
    profile = review.user.player_profile if review.user else None
    return (profile.full_name if profile and profile.full_name else None) or "Người chơi"


@router.get("/{venue_id}/reviews", response_model=List[ReviewResponse])
def get_venue_reviews(venue_id: int, db: Session = Depends(deps.get_db)):
    reviews = db.query(Review).filter(Review.venue_id == venue_id).order_by(Review.created_at.desc()).all()
    return [
        ReviewResponse(
            id=r.id, user_id=r.user_id, rating=r.rating, comment=r.comment,
            created_at=r.created_at, author_name=_review_author(r),
        )
        for r in reviews
    ]


@router.post("/{venue_id}/reviews", response_model=ReviewResponse)
def create_venue_review(
    venue_id: int,
    review_in: ReviewCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Đánh giá cụm sân. Chỉ người đã hoàn thành ít nhất một lượt chơi tại cụm sân mới được đánh giá;
    mỗi người có một đánh giá cho mỗi cụm sân (gửi lại sẽ cập nhật đánh giá cũ).
    """
    from app.models.booking import Booking, BookingDetail

    get_venue_or_404(db, venue_id)
    has_played = (
        db.query(Booking.id)
        .join(BookingDetail, BookingDetail.booking_id == Booking.id)
        .join(Court, Court.id == BookingDetail.court_id)
        .filter(
            Booking.user_id == current_user.id, Booking.source == "ONLINE",
            Booking.status == "COMPLETED", Court.venue_id == venue_id,
        )
        .first()
    )
    if not has_played:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn chỉ có thể đánh giá sau khi đã hoàn thành một lượt chơi tại cụm sân này.",
        )

    review = db.query(Review).filter(Review.venue_id == venue_id, Review.user_id == current_user.id).first()
    if review is None:
        review = Review(user_id=current_user.id, venue_id=venue_id)
        db.add(review)
    review.rating = review_in.rating
    review.comment = (review_in.comment or "").strip() or None
    db.commit()
    db.refresh(review)
    return ReviewResponse(
        id=review.id, user_id=review.user_id, rating=review.rating, comment=review.comment,
        created_at=review.created_at, author_name=_review_author(review),
    )
