"""Giới hạn số lần đăng nhập sai theo (IP, email) trong một cửa sổ thời gian."""
import threading
import time
from typing import Dict, List

from app.core.config import settings
from app.core.redis_client import get_redis


class LoginRateLimiter:
    def __init__(self):
        self._failures: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(identifier: str) -> str:
        return f"login_fail:{identifier}"

    def retry_after(self, identifier: str) -> int:
        """Số giây còn phải chờ; 0 nếu chưa bị chặn."""
        limit, window = settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_WINDOW_SECONDS
        client = get_redis()
        if client is not None:
            try:
                key = self._key(identifier)
                if int(client.get(key) or 0) >= limit:
                    return max(1, int(client.ttl(key)))
                return 0
            except Exception:
                pass  # Redis lỗi tạm thời: dùng bộ đếm trong bộ nhớ
        now = time.time()
        with self._lock:
            recent = [t for t in self._failures.get(identifier, []) if now - t < window]
            self._failures[identifier] = recent
            if len(recent) >= limit:
                return max(1, int(window - (now - recent[0])))
        return 0

    def register_failure(self, identifier: str) -> None:
        client = get_redis()
        if client is not None:
            try:
                key = self._key(identifier)
                if client.incr(key) == 1:
                    client.expire(key, settings.LOGIN_WINDOW_SECONDS)
                return
            except Exception:
                pass
        with self._lock:
            self._failures.setdefault(identifier, []).append(time.time())

    def reset(self, identifier: str) -> None:
        client = get_redis()
        if client is not None:
            try:
                client.delete(self._key(identifier))
            except Exception:
                pass
        with self._lock:
            self._failures.pop(identifier, None)

    def clear_all(self) -> None:
        """Dùng cho kiểm thử."""
        with self._lock:
            self._failures.clear()


login_rate_limiter = LoginRateLimiter()
