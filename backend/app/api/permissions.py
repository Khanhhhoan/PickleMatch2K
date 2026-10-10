"""
Kiểm tra quyền sở hữu tài nguyên theo cụm sân.

- ADMIN: mọi cụm sân.
- OWNER: chỉ cụm sân có owner_id là chính mình.
- STAFF: chỉ cụm sân được phân công trong staff_profile.venue_id.
"""
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.user import User, UserRole
from app.models.venue import Court, Venue


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def managed_venue_ids(db: Session, user: User) -> Optional[List[int]]:
    """Danh sách id cụm sân người dùng được quản lý; None nghĩa là tất cả (ADMIN)."""
    if user.role == UserRole.ADMIN.value:
        return None
    if user.role == UserRole.OWNER.value:
        return [row[0] for row in db.query(Venue.id).filter(Venue.owner_id == user.id).all()]
    if user.role == UserRole.STAFF.value:
        venue_id = user.staff_profile.venue_id if user.staff_profile else None
        return [venue_id] if venue_id else []
    return []


def can_manage_venue(user: User, venue: Venue, *, allow_staff: bool) -> bool:
    if user.role == UserRole.ADMIN.value:
        return True
    if user.role == UserRole.OWNER.value:
        return venue.owner_id == user.id
    if allow_staff and user.role == UserRole.STAFF.value:
        return bool(user.staff_profile and user.staff_profile.venue_id == venue.id)
    return False


def get_venue_or_404(db: Session, venue_id: int) -> Venue:
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy cụm sân")
    return venue


def require_venue_owner(db: Session, user: User, venue_id: int) -> Venue:
    """Cấu hình cụm sân (thông tin, sân, giá, ảnh, nhân viên): chỉ ADMIN hoặc chính chủ sân."""
    venue = get_venue_or_404(db, venue_id)
    if not can_manage_venue(user, venue, allow_staff=False):
        raise _forbidden("Bạn chỉ có thể quản lý cụm sân do mình làm chủ.")
    return venue


def require_venue_staff(db: Session, user: User, venue_id: int) -> Venue:
    """Nghiệp vụ tại quầy (đơn đặt, check-in, hoàn cọc): ADMIN, chủ sân, hoặc nhân viên được phân công."""
    venue = get_venue_or_404(db, venue_id)
    if not can_manage_venue(user, venue, allow_staff=True):
        raise _forbidden("Bạn không có quyền thao tác trên cụm sân này.")
    return venue


def require_court_staff(db: Session, user: User, court_id: int) -> Court:
    court = db.query(Court).filter(Court.id == court_id).first()
    if not court:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy sân")
    require_venue_staff(db, user, court.venue_id)
    return court


def booking_venue_ids(booking: Booking) -> List[int]:
    return sorted({d.court.venue_id for d in booking.details if d.court})


def require_booking_staff(db: Session, user: User, booking: Booking) -> None:
    """Người dùng phải có quyền tại quầy trên MỌI cụm sân mà đơn đặt liên quan."""
    venue_ids = booking_venue_ids(booking)
    if not venue_ids:
        if user.role != UserRole.ADMIN.value:
            raise _forbidden("Đơn đặt không gắn với cụm sân nào bạn quản lý.")
        return
    for venue_id in venue_ids:
        require_venue_staff(db, user, venue_id)
