from datetime import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.api import deps
from app.api.permissions import managed_venue_ids, require_venue_owner
from app.core.security import get_password_hash, verify_password
from app.ml.features import PLAY_STYLES, PURPOSES
from app.models.user import OwnerProfile, PlayerProfile, StaffProfile, User, UserRole
from app.models.venue import Court, OperatingHour, PriceRule, Venue
from app.schemas.user import (
    ActiveStatusUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    ChangePasswordRequest,
    ProfileUpdateRequest,
    StaffCreate,
    StaffUpdate,
    UserResponse,
)
from app.services.user_service import create_user, delete_or_deactivate_user, get_user_by_email

router = APIRouter()

admin_only = deps.RoleChecker([UserRole.ADMIN.value])
owner_or_admin = deps.RoleChecker([UserRole.OWNER.value, UserRole.ADMIN.value])

PLAYER_FIELDS = {
    "full_name", "phone", "skill_level", "play_style", "matches_played", "matches_won",
    "date_of_birth", "latitude", "longitude", "purpose",
}
OWNER_FIELDS = {"full_name", "phone", "company_name", "bank_account"}
STAFF_FIELDS = {"full_name", "phone"}


def _ensure_email_free(db: Session, email: str, exclude_user_id: int) -> None:
    existing = get_user_by_email(db, email)
    if existing and existing.id != exclude_user_id:
        raise HTTPException(status_code=400, detail="Email này đã được sử dụng bởi tài khoản khác.")


def _ensure_profile(db: Session, user: User):
    """Bảo đảm tài khoản có hồ sơ đúng với vai trò hiện tại và trả về hồ sơ đó."""
    if user.role == UserRole.PLAYER.value:
        if not user.player_profile:
            user.player_profile = PlayerProfile(user_id=user.id)
        return user.player_profile
    if user.role == UserRole.OWNER.value:
        if not user.owner_profile:
            user.owner_profile = OwnerProfile(user_id=user.id)
        return user.owner_profile
    if user.role == UserRole.STAFF.value:
        if not user.staff_profile:
            user.staff_profile = StaffProfile(user_id=user.id)
        return user.staff_profile
    return None


# ==========================================
# CURRENT USER
# ==========================================

@router.get("/profile-options")
def get_profile_options():
    """Các giá trị hợp lệ cho hồ sơ người chơi (dùng chung với mô hình ghép cặp)."""
    return {"purposes": PURPOSES, "play_styles": PLAY_STYLES}


@router.get("/me", response_model=UserResponse)
def read_user_me(current_user: User = Depends(deps.get_current_active_user)):
    return current_user


@router.put("/me/profile", response_model=UserResponse)
def update_my_profile(
    profile_data: ProfileUpdateRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Cập nhật hồ sơ của chính mình (trường áp dụng tùy theo vai trò)."""
    allowed = {
        UserRole.PLAYER.value: PLAYER_FIELDS,
        UserRole.OWNER.value: OWNER_FIELDS,
        UserRole.STAFF.value: STAFF_FIELDS,
    }.get(current_user.role)
    profile = _ensure_profile(db, current_user)
    if allowed is None or profile is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vai trò này không có hồ sơ để cập nhật.")

    changes = {k: v for k, v in profile_data.model_dump(exclude_unset=True).items() if k in allowed}
    for field, value in changes.items():
        setattr(profile, field, value)

    if current_user.role == UserRole.PLAYER.value:
        played, won = profile.matches_played or 0, profile.matches_won or 0
        if won > played:
            raise HTTPException(status_code=400, detail="Số trận thắng không thể lớn hơn số trận đã chơi.")

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/change-password")
def change_my_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng. Vui lòng kiểm tra lại.")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải khác mật khẩu hiện tại.")

    current_user.password_hash = get_password_hash(payload.new_password)
    db.commit()
    return {"message": "Đổi mật khẩu thành công!"}


# ==========================================
# ADMIN - USER MANAGEMENT
# ==========================================

@router.get("", response_model=list[UserResponse])
@router.get("/admin/users", response_model=list[UserResponse])
def get_all_users_admin(db: Session = Depends(deps.get_db), _: User = Depends(admin_only)):
    # Nạp theo lô mọi thứ UserResponse đọc tới (kể cả tên cụm sân và chủ sân của nhân viên): số truy vấn cố định
    return (
        db.query(User)
        .options(
            selectinload(User.player_profile),
            selectinload(User.owner_profile),
            selectinload(User.staff_profile).selectinload(StaffProfile.venue).selectinload(Venue.owner).selectinload(User.owner_profile),
        )
        .order_by(User.id.desc())
        .all()
    )


@router.post("/admin/users", response_model=UserResponse)
def admin_create_user(
    user_data: AdminUserCreate,
    db: Session = Depends(deps.get_db),
    _: User = Depends(admin_only),
):
    """Admin tạo tài khoản với vai trò bất kỳ. Chủ sân mới được cấp sẵn một cụm sân khởi tạo."""
    role = user_data.role.value
    if role == UserRole.STAFF.value:
        if not user_data.venue_id:
            raise HTTPException(status_code=400, detail="Nhân viên phải được phân công vào một cụm sân.")
        if not db.query(Venue.id).filter(Venue.id == user_data.venue_id).first():
            raise HTTPException(status_code=404, detail="Không tìm thấy cụm sân được phân công.")

    new_user = create_user(
        db,
        email=user_data.email,
        password=user_data.password,
        role=role,
        full_name=user_data.full_name,
        phone=user_data.phone,
        venue_id=user_data.venue_id if role == UserRole.STAFF.value else None,
        is_active=user_data.is_active,
        commit=False,
    )
    db.refresh(new_user)

    if role == UserRole.PLAYER.value and new_user.player_profile:
        new_user.player_profile.skill_level = user_data.skill_level
        new_user.player_profile.play_style = user_data.play_style
    elif role == UserRole.OWNER.value and new_user.owner_profile:
        new_user.owner_profile.company_name = user_data.company_name
        new_user.owner_profile.bank_account = user_data.bank_account

        display = user_data.company_name or user_data.full_name or user_data.email.split("@")[0]
        venue = Venue(
            name=user_data.venue_name or f"Cụm Sân {display}",
            address=user_data.venue_address or "Chưa cập nhật địa chỉ",
            description=None,
            owner_id=new_user.id,
            # Chưa có địa chỉ thì chưa hiển thị công khai; chủ sân bổ sung thông tin rồi tự bật hoạt động
            status="ACTIVE" if user_data.venue_address else "INACTIVE",
        )
        db.add(venue)
        db.flush()
        for i in range(1, 5):
            db.add(Court(venue_id=venue.id, name=f"Sân {i}", status="ACTIVE"))
        for day in range(7):
            db.add(OperatingHour(venue_id=venue.id, day_of_week=day, open_time=time(6, 0), close_time=time(22, 0)))
        db.add(PriceRule(venue_id=venue.id, rule_type="BASE", price=150000))

    db.commit()
    db.refresh(new_user)
    return new_user


@router.put("/admin/users/{user_id}", response_model=UserResponse)
def admin_update_user(
    user_id: int,
    user_data: AdminUserUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(admin_only),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    changes = user_data.model_dump(exclude_unset=True)

    if changes.get("email") and changes["email"].lower() != target.email.lower():
        _ensure_email_free(db, changes["email"], user_id)
        target.email = changes["email"].strip().lower()
    if changes.get("password"):
        target.password_hash = get_password_hash(changes["password"])
    if changes.get("role") is not None:
        new_role = changes["role"].value
        if target.id == current_user.id and new_role != UserRole.ADMIN.value:
            raise HTTPException(status_code=400, detail="Không thể tự hạ quyền tài khoản Quản trị viên đang đăng nhập.")
        target.role = new_role
    if changes.get("is_active") is not None:
        if target.id == current_user.id and not changes["is_active"]:
            raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản đang đăng nhập.")
        target.is_active = changes["is_active"]

    profile = _ensure_profile(db, target)
    if profile is not None:
        for field in ("full_name", "phone"):
            if field in changes:
                setattr(profile, field, changes[field])
        if target.role == UserRole.PLAYER.value:
            for field in ("skill_level", "play_style"):
                if changes.get(field) is not None:
                    setattr(profile, field, changes[field])
        elif target.role == UserRole.OWNER.value:
            for field in ("company_name", "bank_account"):
                if field in changes:
                    setattr(profile, field, changes[field])
        elif target.role == UserRole.STAFF.value and "venue_id" in changes:
            if changes["venue_id"] and not db.query(Venue.id).filter(Venue.id == changes["venue_id"]).first():
                raise HTTPException(status_code=404, detail="Không tìm thấy cụm sân được phân công.")
            profile.venue_id = changes["venue_id"] or None

    db.commit()
    db.refresh(target)
    return target


@router.put("/admin/users/{user_id}/active", response_model=UserResponse)
def admin_set_user_active(
    user_id: int,
    payload: ActiveStatusUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(admin_only),
):
    """Khóa hoặc mở khóa tài khoản. Tài khoản bị khóa không đăng nhập và không gọi được API."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if target.id == current_user.id and not payload.is_active:
        raise HTTPException(status_code=400, detail="Không thể tự khóa tài khoản đang đăng nhập.")
    target.is_active = payload.is_active
    db.commit()
    db.refresh(target)
    return target


@router.delete("/admin/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(admin_only),
):
    """
    Xóa tài khoản chưa phát sinh dữ liệu. Tài khoản đã có đơn đặt, phòng đấu, đánh giá hoặc
    đang sở hữu cụm sân sẽ chỉ bị khóa để không làm mất dữ liệu lịch sử.
    """
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Không thể tự xóa tài khoản Quản trị viên đang đăng nhập")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    outcome = delete_or_deactivate_user(db, target)
    if outcome == "deactivated":
        return {"status": "deactivated", "message": f"Tài khoản #{user_id} đã có dữ liệu lịch sử nên được khóa thay vì xóa."}
    return {"status": "success", "message": f"Đã xóa tài khoản #{user_id} thành công"}


# ==========================================
# OWNER - STAFF MANAGEMENT
# ==========================================

def _get_managed_staff(db: Session, current_user: User, staff_user_id: int) -> User:
    staff = db.query(User).filter(User.id == staff_user_id, User.role == UserRole.STAFF.value).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên")
    venue_ids = managed_venue_ids(db, current_user)
    if venue_ids is not None:
        if not staff.staff_profile or staff.staff_profile.venue_id not in venue_ids:
            raise HTTPException(status_code=403, detail="Bạn không có quyền quản lý nhân viên này")
    return staff


@router.get("/owner/staff", response_model=list[UserResponse])
def get_owner_staff_list(db: Session = Depends(deps.get_db), current_user: User = Depends(owner_or_admin)):
    """Danh sách nhân viên thuộc các cụm sân của chủ sân đang đăng nhập."""
    query = db.query(User).filter(User.role == UserRole.STAFF.value)
    venue_ids = managed_venue_ids(db, current_user)
    if venue_ids is not None:
        if not venue_ids:
            return []
        query = query.join(StaffProfile, User.id == StaffProfile.user_id).filter(StaffProfile.venue_id.in_(venue_ids))
    return query.order_by(User.id.desc()).all()


@router.post("/owner/staff", response_model=UserResponse)
def create_owner_staff(
    staff_data: StaffCreate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Tạo tài khoản nhân viên gắn với một cụm sân của chủ sân."""
    require_venue_owner(db, current_user, staff_data.venue_id)
    return create_user(
        db,
        email=staff_data.email,
        password=staff_data.password,
        role=UserRole.STAFF.value,
        full_name=staff_data.full_name,
        phone=staff_data.phone,
        venue_id=staff_data.venue_id,
    )


@router.put("/owner/staff/{staff_user_id}", response_model=UserResponse)
def update_owner_staff(
    staff_user_id: int,
    staff_data: StaffUpdate,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    staff = _get_managed_staff(db, current_user, staff_user_id)
    changes = staff_data.model_dump(exclude_unset=True)

    if changes.get("email") and changes["email"].lower() != staff.email.lower():
        _ensure_email_free(db, changes["email"], staff_user_id)
        staff.email = changes["email"].strip().lower()
    if changes.get("password"):
        staff.password_hash = get_password_hash(changes["password"])

    profile = _ensure_profile(db, staff)
    for field in ("full_name", "phone"):
        if field in changes:
            setattr(profile, field, changes[field])
    if changes.get("venue_id"):
        require_venue_owner(db, current_user, changes["venue_id"])
        profile.venue_id = changes["venue_id"]

    db.commit()
    db.refresh(staff)
    return staff


@router.delete("/owner/staff/{staff_user_id}")
def delete_owner_staff(
    staff_user_id: int,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(owner_or_admin),
):
    """Xóa nhân viên; nếu nhân viên đã tạo đơn tại quầy thì chỉ khóa tài khoản để giữ lịch sử."""
    staff = _get_managed_staff(db, current_user, staff_user_id)
    outcome = delete_or_deactivate_user(db, staff)
    if outcome == "deactivated":
        return {"status": "deactivated", "message": f"Nhân viên #{staff_user_id} đã có lịch sử thao tác nên được khóa thay vì xóa."}
    return {"status": "success", "message": f"Đã xóa tài khoản nhân viên #{staff_user_id} thành công"}
