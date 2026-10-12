import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.ml.features import PURPOSES
from app.models.user import UserRole

_PHONE_RE = re.compile(r"^\+?\d{9,12}$")


def _clean_optional_text(value):
    """Chuỗi rỗng từ form được coi là 'không nhập'."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _validate_phone(value: Optional[str]) -> Optional[str]:
    value = _clean_optional_text(value)
    if value is None:
        return None
    compact = re.sub(r"[\s.\-]", "", value)
    if not _PHONE_RE.match(compact):
        raise ValueError("Số điện thoại không hợp lệ (9-12 chữ số).")
    return compact


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class PlayerProfileBase(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    skill_level: Optional[float] = None
    play_style: Optional[str] = None
    matches_played: Optional[int] = None
    matches_won: Optional[int] = None
    win_rate: Optional[float] = None
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    purpose: Optional[str] = None


class PlayerProfileResponse(PlayerProfileBase):
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class OwnerProfileBase(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    bank_account: Optional[str] = None


class OwnerProfileResponse(OwnerProfileBase):
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class StaffProfileBase(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    venue_id: Optional[int] = None
    venue_name: Optional[str] = None
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None


class StaffProfileResponse(StaffProfileBase):
    user_id: int

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: int
    email: str  # Chỉ kiểm tra định dạng ở đầu vào; dữ liệu cũ không hợp chuẩn vẫn phải hiển thị được
    role: str
    is_active: bool = True
    player_profile: Optional[PlayerProfileResponse] = None
    owner_profile: Optional[OwnerProfileResponse] = None
    staff_profile: Optional[StaffProfileResponse] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    """Đăng ký công khai: luôn tạo tài khoản Người chơi."""
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = None
    role: Optional[str] = None

    _phone = field_validator("phone", mode="before")(_validate_phone)
    _name = field_validator("full_name", mode="before")(_clean_optional_text)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=128)


class ProfileUpdateRequest(BaseModel):
    """Cập nhật hồ sơ của chính mình. Trường nào áp dụng phụ thuộc vai trò; trường không gửi thì giữ nguyên."""
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = None
    # Người chơi
    skill_level: Optional[float] = Field(default=None, ge=1.0, le=8.0)
    play_style: Optional[str] = Field(default=None, max_length=60)
    matches_played: Optional[int] = Field(default=None, ge=0, le=100000)
    matches_won: Optional[int] = Field(default=None, ge=0, le=100000)
    date_of_birth: Optional[date] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    purpose: Optional[str] = None
    # Chủ sân
    company_name: Optional[str] = Field(default=None, max_length=160)
    bank_account: Optional[str] = Field(default=None, max_length=160)

    model_config = ConfigDict(extra="ignore")

    _phone = field_validator("phone", mode="before")(_validate_phone)
    _text = field_validator(
        "full_name", "play_style", "company_name", "bank_account", "date_of_birth", "purpose", mode="before"
    )(_clean_optional_text)

    @field_validator("purpose")
    @classmethod
    def _known_purpose(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PURPOSES:
            raise ValueError(f"Mục đích chơi phải là một trong: {', '.join(PURPOSES)}.")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def _dob_in_past(cls, value: Optional[date]) -> Optional[date]:
        if value is not None and not (date(1900, 1, 1) <= value <= date.today()):
            raise ValueError("Ngày sinh không hợp lệ.")
        return value

    @model_validator(mode="after")
    def _won_not_above_played(self):
        if self.matches_played is not None and self.matches_won is not None and self.matches_won > self.matches_played:
            raise ValueError("Số trận thắng không thể lớn hơn số trận đã chơi.")
        return self


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: UserRole = UserRole.PLAYER
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = None
    is_active: bool = True
    # Người chơi
    skill_level: Optional[float] = Field(default=None, ge=1.0, le=8.0)
    play_style: Optional[str] = Field(default=None, max_length=60)
    # Chủ sân
    company_name: Optional[str] = Field(default=None, max_length=160)
    bank_account: Optional[str] = Field(default=None, max_length=160)
    venue_name: Optional[str] = Field(default=None, max_length=160)
    venue_address: Optional[str] = Field(default=None, max_length=255)
    # Nhân viên
    venue_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")

    _phone = field_validator("phone", mode="before")(_validate_phone)
    _text = field_validator(
        "full_name", "play_style", "company_name", "bank_account", "venue_name", "venue_address", mode="before"
    )(_clean_optional_text)


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    role: Optional[UserRole] = None
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    skill_level: Optional[float] = Field(default=None, ge=1.0, le=8.0)
    play_style: Optional[str] = Field(default=None, max_length=60)
    company_name: Optional[str] = Field(default=None, max_length=160)
    bank_account: Optional[str] = Field(default=None, max_length=160)
    venue_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")

    _phone = field_validator("phone", mode="before")(_validate_phone)
    _text = field_validator("password", "full_name", "play_style", "company_name", "bank_account", mode="before")(
        _clean_optional_text
    )


class StaffCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = None
    venue_id: int

    _phone = field_validator("phone", mode="before")(_validate_phone)
    _name = field_validator("full_name", mode="before")(_clean_optional_text)


class StaffUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = None
    venue_id: Optional[int] = None

    model_config = ConfigDict(extra="ignore")

    _phone = field_validator("phone", mode="before")(_validate_phone)
    _text = field_validator("password", "full_name", mode="before")(_clean_optional_text)


class ActiveStatusUpdate(BaseModel):
    is_active: bool
