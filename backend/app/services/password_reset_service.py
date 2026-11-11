"""
Quên mật khẩu của người chơi: chuẩn bị thư có liên kết đặt lại, rồi đặt mật khẩu mới bằng liên kết đó.

Mã trong liên kết ký bằng khóa riêng (security.create_password_reset_token), hạn 30 phút theo đồng hồ nghiệp vụ, gắn
với dấu vân tay của mật khẩu lúc xin: mật khẩu đổi là mọi liên kết cũ hết hiệu lực, nên không cần lưu mã trong CSDL.
Chỉ tài khoản người chơi đang hoạt động, có email không thuộc danh sách chặn (tài khoản mẫu, tên miền dùng thử) mới
nhận thư; nơi gọi trả cùng một câu cho mọi email để không ai dò được email nào có tài khoản.
"""
import hmac
import html
from fnmatch import fnmatch
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.models.user import User, UserRole
from app.services.email_service import EmailMessage, email_ready
from app.services.user_service import get_user_by_email, normalize_email
from app.utils.timeutils import now_utc

RESET_LINK_MINUTES = security.PASSWORD_RESET_MINUTES
GENERIC_MESSAGE = ("Nếu email này thuộc một tài khoản người chơi, chúng tôi đã gửi hướng dẫn đặt lại mật khẩu. "
                   "Vui lòng kiểm tra hộp thư, kể cả mục Spam.")
INVALID_LINK = "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Hãy yêu cầu liên kết mới."
UNAVAILABLE = "Chức năng quên mật khẩu đang tạm ngưng. Vui lòng liên hệ quản trị viên."
DONE_MESSAGE = "Đã đặt lại mật khẩu. Hãy đăng nhập bằng mật khẩu mới."
SUBJECT = "Đặt lại mật khẩu PickleMatch2K"


def available() -> bool:
    """Gửi được thư đặt lại mật khẩu chưa: đã cấu hình gửi thư, và ở bản chạy thật liên kết phải trỏ về địa chỉ https
    (thiếu WEB_APP_URL thì liên kết sẽ trỏ về localhost)."""
    return email_ready() and (not settings.is_production or settings.WEB_APP_URL.startswith("https://"))


def is_blocked(email: str) -> bool:
    """Địa chỉ không bao giờ nhận thư đặt lại mật khẩu (PASSWORD_RESET_BLOCKED_EMAILS)."""
    address = normalize_email(email)
    return any(fnmatch(address, pattern) for pattern in settings.password_reset_blocked_patterns)


def _can_reset(user: Optional[User]) -> bool:
    return user is not None and user.is_active and user.role == UserRole.PLAYER.value


def prepare_reset_email(db: Session, email: str) -> Optional[EmailMessage]:
    """Thư đặt lại mật khẩu cho email này; None nếu không gửi (không có tài khoản người chơi đang hoạt động, hoặc
    địa chỉ nằm trong danh sách chặn)."""
    user = get_user_by_email(db, email)
    if not _can_reset(user) or is_blocked(user.email):
        return None
    token = security.create_password_reset_token(user.id, user.password_hash, now_utc())
    link = f"{settings.WEB_APP_URL.rstrip('/')}/reset-password?token={token}"
    name = (user.player_profile.full_name if user.player_profile else None) or "bạn"
    return EmailMessage(to=user.email, subject=SUBJECT, text=_text(name, link), html=_html(name, link))


def reset_password(db: Session, token: str, new_password: str) -> User:
    """Đặt mật khẩu mới bằng mã trong liên kết. 400 INVALID_LINK nếu mã sai, hết hạn, đã dùng (mật khẩu đã đổi) hoặc
    tài khoản không còn là người chơi đang hoạt động."""
    parsed = security.read_password_reset_token(token, now_utc())
    user = db.get(User, parsed[0]) if parsed else None
    if not parsed or not _can_reset(user) or not hmac.compare_digest(
        parsed[1], security.password_fingerprint(user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=INVALID_LINK)
    user.password_hash = security.get_password_hash(new_password)
    db.commit()
    login_rate_limiter.forget_email(normalize_email(user.email))  # bị khóa vì đăng nhập sai thì mở lại luôn
    return user


def _text(name: str, link: str) -> str:
    return (
        f"Xin chào {name},\n\n"
        "Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản PickleMatch2K của bạn. "
        "Mở liên kết dưới đây để đặt mật khẩu mới:\n\n"
        f"{link}\n\n"
        f"Liên kết có hiệu lực trong {RESET_LINK_MINUTES} phút và chỉ dùng được một lần.\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua thư này; mật khẩu hiện tại vẫn giữ nguyên.\n\n"
        "PickleMatch2K\n"
    )


def _html(name: str, link: str) -> str:
    safe_name, safe_link = html.escape(name), html.escape(link, quote=True)
    muted = "margin:0 0 12px;font-size:13px;color:#52525b"
    button = ("display:inline-block;background:#09090b;color:#ffffff;text-decoration:none;font-weight:bold;"
              "padding:12px 22px;border-radius:12px")
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:0 auto;color:#18181b;'
        'line-height:1.5">'
        '<h2 style="font-size:20px;margin:0 0 16px">Đặt lại mật khẩu</h2>'
        f'<p style="margin:0 0 12px">Xin chào {safe_name},</p>'
        '<p style="margin:0 0 20px">Chúng tôi nhận được yêu cầu đặt lại mật khẩu cho tài khoản PickleMatch2K '
        "của bạn.</p>"
        f'<p style="margin:0 0 20px"><a href="{safe_link}" style="{button}">Đặt lại mật khẩu</a></p>'
        f'<p style="{muted}">Liên kết có hiệu lực trong {RESET_LINK_MINUTES} phút và chỉ dùng được một lần. '
        "Nếu nút không bấm được, mở địa chỉ sau:</p>"
        f'<p style="margin:0 0 20px;font-size:12px;word-break:break-all">'
        f'<a href="{safe_link}" style="color:#2563eb">{safe_link}</a></p>'
        f'<p style="{muted}">Nếu bạn không yêu cầu, hãy bỏ qua thư này; mật khẩu hiện tại vẫn giữ nguyên.</p>'
        "</div>"
    )
