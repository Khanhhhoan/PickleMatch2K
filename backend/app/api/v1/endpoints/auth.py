from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.models.user import UserRole
from app.schemas.token import Token
from app.schemas.user import RegisterRequest, UserResponse
from app.services.user_service import create_user, get_user_by_email, normalize_email

router = APIRouter()


@router.post("/register", response_model=UserResponse)
def register(user_in: RegisterRequest, db: Session = Depends(deps.get_db)):
    """
    Đăng ký công khai chỉ tạo tài khoản Người chơi (PLAYER).
    Tài khoản Chủ sân, Nhân viên và Admin do quản trị viên hoặc chủ sân cấp.
    """
    if user_in.role and user_in.role != UserRole.PLAYER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Người dùng tự do chỉ có thể đăng ký tài khoản Người chơi (Player). "
                   "Tài khoản Chủ sân (Owner) và Admin do ban quản trị cấp phép.",
        )
    return create_user(
        db,
        email=user_in.email,
        password=user_in.password,
        role=UserRole.PLAYER.value,
        full_name=user_in.full_name,
        phone=user_in.phone,
    )


@router.post("/login", response_model=Token)
def login_access_token(
    request: Request,
    db: Session = Depends(deps.get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Đăng nhập kiểu OAuth2 password, trả về access token."""
    client_ip = request.client.host if request.client else "unknown"
    identifier = f"{client_ip}:{normalize_email(form_data.username)}"

    retry_after = login_rate_limiter.retry_after(identifier)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Bạn đã đăng nhập sai quá nhiều lần. Vui lòng thử lại sau {retry_after} giây.",
            headers={"Retry-After": str(retry_after)},
        )

    user = get_user_by_email(db, email=form_data.username)
    if not user or not security.verify_password(form_data.password, user.password_hash):
        login_rate_limiter.register_failure(identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email hoặc mật khẩu không chính xác.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.")

    login_rate_limiter.reset(identifier)
    if security.needs_rehash(user.password_hash):
        # Nâng cấp mật khẩu lưu theo định dạng cũ sang bcrypt
        user.password_hash = security.get_password_hash(form_data.password)
        db.commit()

    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        ),
        "token_type": "bearer",
    }
