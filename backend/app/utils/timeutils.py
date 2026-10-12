"""Mọi phép tính ngày/giờ nghiệp vụ dùng giờ Việt Nam (UTC+7); mốc thời gian lưu CSDL là UTC."""
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional

VN_TZ = timezone(timedelta(hours=7))
VN_TZ_NAME = "Asia/Ho_Chi_Minh"  # tên múi giờ cho các phép tính ngày thực hiện ngay trong SQL

# Nguồn thời gian thay thế, chỉ dùng trong kiểm thử để "đứng" hoặc "tua" đồng hồ (xem tests/conftest.py).
_clock: Optional[Callable[[], datetime]] = None


def set_clock(clock: Optional[Callable[[], datetime]]) -> None:
    global _clock
    _clock = clock


def now_utc() -> datetime:
    if _clock is not None:
        return _clock().astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def now_vn() -> datetime:
    return now_utc().astimezone(VN_TZ)


def today_vn() -> date:
    return now_vn().date()


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Chuẩn hóa datetime đọc từ CSDL về UTC có múi giờ (giá trị naive được hiểu là UTC)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def vn_datetime(day: date, moment: time) -> datetime:
    """Ghép ngày + giờ của một khung giờ sân thành datetime theo giờ Việt Nam."""
    return datetime.combine(day, moment, tzinfo=VN_TZ)


def vn_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Khoảng [đầu ngày, đầu ngày kế tiếp) của một ngày Việt Nam, biểu diễn theo UTC."""
    start = datetime.combine(day, time.min, tzinfo=VN_TZ)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)
