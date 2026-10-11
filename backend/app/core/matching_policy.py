"""Tham số và quy tắc của chức năng ghép trận."""
from datetime import date, time
from typing import Iterable, List, Optional

from app.ml.features import DAYS

# Một phòng đấu được "mô hình đề xuất" cho người xem khi độ phù hợp (0-100) đạt mức này.
# Bộ phân loại tách hai lớp ở 50%; mức 70% chỉ giữ lại những phòng mô hình đánh giá rõ ràng là phù hợp.
RECOMMEND_MIN_COMPATIBILITY = 70.0

# Khung rảnh trong hồ sơ chia mỗi ngày thành ba buổi: sáng trước 12:00, chiều 12:00 - 17:00, tối từ 17:00.
# Mỗi dòng: (buổi, giờ bắt đầu, giờ kết thúc); None = tới hết ngày.
PERIOD_HOURS = (
    ("morning", time(0, 0), time(12, 0)),
    ("afternoon", time(12, 0), time(17, 0)),
    ("evening", time(17, 0), None),
)


def slots_of_window(day: date, start: time, end: time) -> List[str]:
    """Các khung rảnh (thứ_buổi) mà một khoảng giờ chơi chạm tới: thứ Ba 16:00 - 18:00 -> tue_afternoon, tue_evening."""
    weekday = DAYS[day.weekday()]
    return [
        f"{weekday}_{period}"
        for period, begins, ends in PERIOD_HOURS
        if end > begins and (ends is None or start < ends)
    ]


def fits_free_time(free_slots: Iterable[str], day: date, start: time, end: time) -> Optional[bool]:
    """
    Giờ chơi có nằm trọn trong các khung mà người chơi đã khai là rảnh hay không.
    None khi người chơi chưa khai khung rảnh nào: không có căn cứ để loại phòng.
    """
    free = set(free_slots)
    if not free:
        return None
    return all(slot in free for slot in slots_of_window(day, start, end))
