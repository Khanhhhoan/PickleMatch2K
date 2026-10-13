from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models.user import OwnerProfile, PlayerProfile, StaffProfile, User, UserRole


def normalize_email(email: str) -> str:
    return email.strip().lower()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(func.lower(User.email) == normalize_email(email)).first()


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: str = UserRole.PLAYER.value,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    venue_id: Optional[int] = None,
    is_active: bool = True,
    commit: bool = True,
) -> User:
    """Tạo tài khoản kèm hồ sơ theo vai trò trong MỘT giao dịch. Không gán sẵn dữ liệu giả."""
    if get_user_by_email(db, email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email này đã được sử dụng.")

    user = User(email=normalize_email(email), password_hash=get_password_hash(password), role=role, is_active=is_active)
    db.add(user)
    db.flush()

    if role == UserRole.PLAYER.value:
        db.add(PlayerProfile(user_id=user.id, full_name=full_name, phone=phone))
    elif role == UserRole.OWNER.value:
        db.add(OwnerProfile(user_id=user.id, full_name=full_name, phone=phone))
    elif role == UserRole.STAFF.value:
        db.add(StaffProfile(user_id=user.id, venue_id=venue_id, full_name=full_name, phone=phone))

    if commit:
        db.commit()
        db.refresh(user)
    else:
        db.flush()
    return user


def user_has_history(db: Session, user_id: int) -> bool:
    """
    Tài khoản đã phát sinh dữ liệu (đơn đặt, phòng đấu, đánh giá, cụm sân sở hữu, thao tác tại quầy,
    lần kết ca, nhãn khảo sát) thì không được xóa vật lý.
    """
    from sqlalchemy import or_

    from app.models.booking import Booking
    from app.models.match import Match, MatchParticipant
    from app.models.ml import PairFeedback
    from app.models.payment import PaymentTransaction, ShiftClosing
    from app.models.venue import Review, Venue

    checks = (
        db.query(Booking.id).filter(or_(
            Booking.user_id == user_id, Booking.checked_in_by_id == user_id,
            Booking.cancelled_by_id == user_id, Booking.refunded_by_id == user_id,
        )),
        db.query(PaymentTransaction.id).filter(PaymentTransaction.created_by_id == user_id),
        db.query(ShiftClosing.id).filter(ShiftClosing.closed_by_id == user_id),
        db.query(Match.id).filter(Match.creator_id == user_id),
        db.query(MatchParticipant.id).filter(MatchParticipant.user_id == user_id),
        db.query(Review.id).filter(Review.user_id == user_id),
        db.query(Venue.id).filter(Venue.owner_id == user_id),
        db.query(PairFeedback.id).filter(PairFeedback.rater_id == user_id),
    )
    return any(q.first() is not None for q in checks)


def delete_or_deactivate_user(db: Session, user: User) -> str:
    """
    Xóa tài khoản chưa có lịch sử; tài khoản đã có lịch sử thì chỉ khóa (is_active = False)
    để giữ dữ liệu đặt sân, giao dịch phục vụ thống kê và truy vết.
    Trả về "deleted" hoặc "deactivated".
    """
    if user_has_history(db, user.id):
        user.is_active = False
        db.commit()
        return "deactivated"

    db.delete(user)  # hồ sơ theo vai trò được xóa kèm (cascade)
    db.commit()
    return "deleted"
