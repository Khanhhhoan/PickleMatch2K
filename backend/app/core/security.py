import base64
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

import bcrypt
from jose import jwt

from app.core.config import settings

ALGORITHM = "HS256"

# Định dạng cũ: sha256(password + salt cố định) -> 64 ký tự hex. Chỉ còn dùng để nhận diện và
# nâng cấp sang bcrypt ở lần đăng nhập thành công kế tiếp (xem needs_rehash).
_LEGACY_SALT = "pickleball_secure_salt_2026"
_LEGACY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode({"exp": expire, "sub": str(subject)}, settings.SECRET_KEY, algorithm=ALGORITHM)


def _prehash(password: str) -> bytes:
    # bcrypt chỉ dùng 72 byte đầu; băm SHA-256 trước để mật khẩu dài/Unicode không bị cắt cụt.
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def _legacy_hash(password: str) -> str:
    return hashlib.sha256((password + _LEGACY_SALT).encode("utf-8")).hexdigest()


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(_prehash(password), salt).decode("ascii")


def needs_rehash(hashed_password: str) -> bool:
    """True nếu mật khẩu đang lưu ở định dạng cũ và cần băm lại bằng bcrypt."""
    return bool(_LEGACY_HASH_RE.match(hashed_password or ""))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    if needs_rehash(hashed_password):
        return hmac.compare_digest(_legacy_hash(plain_password), hashed_password)
    try:
        return bcrypt.checkpw(_prehash(plain_password), hashed_password.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False
