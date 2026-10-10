"""Kết nối Redis dùng chung (giữ chỗ slot, giới hạn tần suất). Trả về None khi không dùng được Redis."""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("pickleball.redis")

_client = None
_initialised = False


def get_redis():
    """Client Redis nếu REDIS_URL được cấu hình và kết nối được; ngược lại None (dùng bộ nhớ tiến trình)."""
    global _client, _initialised
    if _initialised:
        return _client
    _initialised = True

    if not settings.REDIS_URL:
        logger.warning("REDIS_URL chưa cấu hình: giữ chỗ và giới hạn tần suất lưu trong bộ nhớ (chỉ đúng khi chạy 1 tiến trình).")
        return None
    try:
        import redis

        client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=0.5, socket_timeout=1.0)
        client.ping()
        _client = client
        logger.info("Đã kết nối Redis.")
    except Exception as exc:
        logger.warning("Không kết nối được Redis (%s): chuyển sang lưu trong bộ nhớ tiến trình.", exc)
        _client = None
    return _client


def reset_redis(client: Optional[object] = None) -> None:
    """Dùng cho kiểm thử: gán client giả hoặc buộc kết nối lại."""
    global _client, _initialised
    _client = client
    _initialised = client is not None
