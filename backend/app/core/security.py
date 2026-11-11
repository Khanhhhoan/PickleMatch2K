import base64
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple, Union

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

ALGORITHM = "HS256"
PASSWORD_RESET_TOKEN_TYPE = "pwd_reset"
PASSWORD_RESET_MINUTES = 30

# Định dạng cũ: sha256(password + salt cố định) -> 64 ký tự hex. Chỉ còn dùng để nhận diện và
# nâng cấp sang bcrypt ở lần đăng nhập thành công kế tiếp (xem needs_rehash).
_LEGACY_SALT = "pickleball_secure_salt_2026"
_LEGACY_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def password_fingerprint(password_hash: str) -> str:
    """Dấu vân tay ngắn của mật khẩu đang lưu: mật khẩu đổi thì dấu vân tay đổi. Không suy ra được gì về mật khẩu."""
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), (password_hash or "").encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:16]


def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None, password_hash: Optional[str] = None
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    claims = {"exp": expire, "sub": str(subject)}
    if password_hash is not None:
        # Mật khẩu đổi là token này hết hiệu lực (xem deps.get_user_from_token)
        claims["pwd"] = password_fingerprint(password_hash)
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)


def _password_reset_key() -> str:
    """Khóa ký mã đặt lại mật khẩu, dẫn xuất từ SECRET_KEY: mã đặt lại và token đăng nhập không dùng thay nhau được."""
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), b"password-reset", hashlib.sha256).hexdigest()


def create_password_reset_token(user_id: int, password_hash: str, now: datetime) -> str:
    """Mã trong liên kết đặt lại mật khẩu: hạn PASSWORD_RESET_MINUTES phút tính từ `now`, gắn với mật khẩu hiện tại
    (mật khẩu đổi là mã hết hiệu lực, nên mỗi mã chỉ dùng được một lần)."""
    claims = {
        "sub": str(user_id),
        "pwd": password_fingerprint(password_hash),
        "typ": PASSWORD_RESET_TOKEN_TYPE,
        "exp": int((now + timedelta(minutes=PASSWORD_RESET_MINUTES)).timestamp()),
    }
    return jwt.encode(claims, _password_reset_key(), algorithm=ALGORITHM)


def read_password_reset_token(token: str, now: datetime) -> Optional[Tuple[int, str]]:
    """(id người dùng, dấu vân tay mật khẩu lúc cấp mã) nếu mã đúng chữ ký và còn hạn tại `now`; None nếu không."""
    try:
        # Hạn được so với đồng hồ nghiệp vụ (`now`), không theo giờ máy
        claims = jwt.decode(token, _password_reset_key(), algorithms=[ALGORITHM], options={"verify_exp": False})
        user_id, expires, fingerprint = int(claims["sub"]), int(claims["exp"]), str(claims["pwd"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None
    if claims.get("typ") != PASSWORD_RESET_TOKEN_TYPE or now.timestamp() >= expires:
        return None
    return user_id, fingerprint


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
