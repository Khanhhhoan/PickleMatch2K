"""Giới hạn tần suất: đăng nhập sai theo (IP, email) và số lần xin liên kết đặt lại mật khẩu (theo email, theo IP)."""
import re
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

    def forget_email(self, email: str) -> None:
        """Xóa mọi bộ đếm đăng nhập sai của một email (ở mọi IP), ví dụ sau khi người dùng đặt lại mật khẩu."""
        suffix = f":{email}"
        client = get_redis()
        if client is not None:
            try:
                escaped = re.sub(r"([\[\]*?\\])", r"\\\1", email)  # ký tự đặc biệt của mẫu Redis
                for key in client.scan_iter(match=self._key(f"*:{escaped}")):
                    client.delete(key)
            except Exception:
                pass
        with self._lock:
            for identifier in [i for i in self._failures if i.endswith(suffix)]:
                self._failures.pop(identifier, None)

    def clear_all(self) -> None:
        """Dùng cho kiểm thử."""
        with self._lock:
            self._failures.clear()


class RequestLimiter:
    """Cho phép tối đa `limit` lần trong `window_seconds` giây cho mỗi khóa nhận diện (IP, email...)."""

    def __init__(self, name: str, limit: int, window_seconds: int):
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def hit(self, identifier: str) -> int:
        """Ghi nhận một lần. 0 = cho qua (đã đếm lần này); > 0 = đã đủ số lần, còn phải chờ bấy nhiêu giây."""
        client = get_redis()
        if client is not None:
            try:
                key = f"{self.name}:{identifier}"
                count = client.incr(key)
                if count == 1:
                    client.expire(key, self.window)
                return max(1, int(client.ttl(key))) if count > self.limit else 0
            except Exception:
                pass  # Redis lỗi tạm thời: dùng bộ đếm trong bộ nhớ
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits.get(identifier, []) if now - t < self.window]
            if len(recent) >= self.limit:
                self._hits[identifier] = recent
                return max(1, int(self.window - (now - recent[0])))
            self._hits[identifier] = recent + [now]
        return 0

    def clear_all(self) -> None:
        """Dùng cho kiểm thử."""
        with self._lock:
            self._hits.clear()


login_rate_limiter = LoginRateLimiter()
# Xin liên kết đặt lại mật khẩu: 3 lần / 15 phút cho mỗi email, 10 lần / giờ cho mỗi IP
reset_email_limiter = RequestLimiter("pwd_reset_email", 3, 900)
reset_ip_limiter = RequestLimiter("pwd_reset_ip", 10, 3600)
