"""
Gửi email của hệ thống (hiện chỉ có thư đặt lại mật khẩu).

- EMAIL_BACKEND=file (mặc định): mỗi thư thành một file JSON trong EMAIL_OUTBOX_DIR. Dùng khi chạy ở máy phát triển,
  khi kiểm thử và trên bản demo: không có thư thật nào được gửi đi.
- EMAIL_BACKEND=brevo: gửi qua API HTTPS của Brevo. Render gói miễn phí chặn các cổng SMTP (25, 465, 587) nên không
  gửi thẳng qua Gmail được.

send_email không bao giờ ném lỗi: gửi hỏng thì ghi log (không kèm nội dung thư, vì thư có liên kết đặt lại mật khẩu)
rồi trả False.
"""
import json
import logging
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger("pickleball.email")

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"
BREVO_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str


def _backend() -> str:
    return settings.EMAIL_BACKEND.strip().lower()


def email_ready() -> bool:
    """Đã cấu hình đủ để gửi thư chưa. Giá trị EMAIL_BACKEND lạ được coi là chưa cấu hình."""
    if _backend() == "brevo":
        return bool(settings.BREVO_API_KEY and settings.EMAIL_FROM)
    return _backend() == "file"


def send_email(message: EmailMessage) -> bool:
    """Gửi một thư. True nếu đã gửi (hoặc đã ghi ra thư mục), False nếu không gửi được."""
    if not email_ready():
        logger.warning("Chưa cấu hình gửi email (EMAIL_BACKEND=%s): thư không được gửi.", _backend())
        return False
    try:
        if _backend() == "brevo":
            return _send_with_brevo(message)
        _write_to_outbox(message)
        return True
    except Exception:  # lỗi gửi thư không được làm hỏng yêu cầu của người dùng
        logger.exception("Gửi email không thành công.")
        return False


def _send_with_brevo(message: EmailMessage) -> bool:
    try:
        response = httpx.post(
            BREVO_SEND_URL,
            headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
            json={
                "sender": {"name": settings.EMAIL_FROM_NAME, "email": settings.EMAIL_FROM},
                "to": [{"email": message.to}],
                "subject": message.subject,
                "textContent": message.text,
                "htmlContent": message.html,
            },
            timeout=BREVO_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("Không gọi được Brevo để gửi email: %s", type(exc).__name__)
        return False
    if 200 <= response.status_code < 300:
        return True
    logger.warning("Brevo không nhận gửi email (HTTP %s): %s", response.status_code, response.text[:300])
    return False


def _write_to_outbox(message: EmailMessage) -> None:
    folder = Path(settings.EMAIL_OUTBOX_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    # Tên file bắt đầu bằng thời điểm ghi: sắp theo tên là đúng thứ tự gửi
    path = folder / f"{now:%Y%m%d-%H%M%S-%f}-{secrets.token_hex(2)}.json"
    path.write_text(json.dumps({**asdict(message), "created_at": now.isoformat()}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    logger.info("Đã ghi thư gửi %s vào %s (EMAIL_BACKEND=file, không gửi thật).", message.to, path)
