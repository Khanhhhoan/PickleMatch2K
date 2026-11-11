from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter, reset_email_limiter, reset_ip_limiter
from app.models.user import UserRole
from app.schemas.token import Token
from app.schemas.user import (
    ForgotPasswordRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
)
from app.services import password_reset_service
from app.services.email_service import email_ready, send_email
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
            user.id,
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            password_hash=user.password_hash,  # sau bước băm lại ở trên: đúng mật khẩu đang lưu
        ),
        "token_type": "bearer",
    }


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(deps.get_db),
):
    """
    Gửi liên kết đặt lại mật khẩu tới email của người chơi. Câu trả lời như nhau dù email có tài khoản hay không;
    thư được gửi sau khi đã trả lời nên thời gian phản hồi cũng không lộ điều đó.
    """
    if not email_ready():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=password_reset_service.UNAVAILABLE)

    email = normalize_email(payload.email)
    client_ip = request.client.host if request.client else "unknown"
    for limiter, identifier in ((reset_ip_limiter, client_ip), (reset_email_limiter, email)):
        wait = limiter.hit(identifier)
        if wait:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Bạn đã yêu cầu quá nhiều lần. Vui lòng thử lại sau {-(-wait // 60)} phút.",
                headers={"Retry-After": str(wait)},
            )

    message = password_reset_service.prepare_reset_email(db, email)
    if message is not None:
        background.add_task(send_email, message)
    return {"message": password_reset_service.GENERIC_MESSAGE}


@router.post("/reset-password", response_model=MessageResponse)
def reset_password_with_link(payload: ResetPasswordRequest, db: Session = Depends(deps.get_db)):
    """Đặt mật khẩu mới bằng liên kết trong thư. Mật khẩu đổi là mọi liên kết và phiên đăng nhập cũ hết hiệu lực."""
    password_reset_service.reset_password(db, payload.token, payload.new_password)
    return {"message": password_reset_service.DONE_MESSAGE}
