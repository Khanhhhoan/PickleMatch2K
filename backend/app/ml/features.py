"""
Đặc trưng của mô hình ghép cặp người chơi.

Module này là NGUỒN DUY NHẤT xây dựng đặc trưng, dùng chung cho huấn luyện (train_model.py),
khảo sát thu nhãn và suy luận trên API, để dữ liệu huấn luyện và dữ liệu phục vụ luôn nhất quán.

Bốn đặc trưng (đều đối xứng giữa hai người chơi):
    level_diff     Chênh lệch trình độ DUPR tự khai
    distance_km    Khoảng cách địa lý giữa hai người (hoặc từ người chơi tới sân của phòng đấu)
    purpose_match  Cùng mục đích chơi (giao lưu / luyện tập / thi đấu)
    style_match    Phong cách chơi tương thích
"""
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

FEATURE_NAMES = ["level_diff", "distance_km", "purpose_match", "style_match"]

MAX_DISTANCE_KM = 50.0
UNKNOWN_DISTANCE_KM = 10.0  # dùng khi một trong hai bên chưa khai vị trí (giá trị trung tính, có ghi chú thiếu dữ liệu)

PURPOSES = ["recreational", "practice", "competitive"]

# Tên chuẩn của phong cách chơi và các cách ghi từng xuất hiện trong dữ liệu cũ
PLAY_STYLES = ["Offensive", "Defensive", "All-Round", "Serve & Volley", "Dinking & Control"]
_STYLE_KEYWORDS = [
    ("toàn diện", "All-Round"), ("all-round", "All-Round"), ("all-around", "All-Round"),
    ("giao bóng", "Serve & Volley"), ("serve", "Serve & Volley"),
    ("dinking", "Dinking & Control"), ("kiểm soát", "Dinking & Control"),
    ("phòng thủ", "Defensive"), ("defensive", "Defensive"),
    ("tấn công", "Offensive"), ("offensive", "Offensive"), ("aggressive", "Offensive"), ("power", "Offensive"),
]


def canonical_style(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = value.strip().lower()
    for keyword, style in _STYLE_KEYWORDS:
        if keyword in lowered:
            return style
    return None


@dataclass
class ProfileView:
    """Phần hồ sơ người chơi mà mô hình cần."""
    skill_level: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    purpose: Optional[str] = None
    play_style: Optional[str] = None

    @classmethod
    def from_profile(cls, profile) -> "ProfileView":
        if profile is None:
            return cls()
        return cls(
            skill_level=profile.skill_level,
            latitude=profile.latitude,
            longitude=profile.longitude,
            purpose=profile.purpose if profile.purpose in PURPOSES else None,
            play_style=canonical_style(profile.play_style),
        )

    def missing_fields(self) -> List[str]:
        missing = []
        if self.skill_level is None:
            missing.append("skill_level")
        if self.latitude is None or self.longitude is None:
            missing.append("location")
        if not self.purpose:
            missing.append("purpose")
        if not self.play_style:
            missing.append("play_style")
        return missing


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def style_compatible(a: Optional[str], b: Optional[str]) -> int:
    """Tương thích khi cùng phong cách, hoặc một bên chơi toàn diện."""
    if not a or not b:
        return 0
    return int(a == b or "All-Round" in (a, b))


def pair_features(a: ProfileView, b: ProfileView, distance_km: Optional[float] = None) -> Optional[Dict[str, float]]:
    """
    Vector đặc trưng của một cặp. Trả về None nếu thiếu trình độ của một trong hai người,
    vì không thể ước lượng độ phù hợp khi chưa biết trình độ.
    distance_km: truyền vào khi khoảng cách cần tính tới một điểm khác (ví dụ sân của phòng đấu).
    """
    if a.skill_level is None or b.skill_level is None:
        return None
    if distance_km is None:
        if None in (a.latitude, a.longitude, b.latitude, b.longitude):
            distance_km = UNKNOWN_DISTANCE_KM
        else:
            distance_km = haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
    return {
        "level_diff": round(abs(float(a.skill_level) - float(b.skill_level)), 2),
        "distance_km": round(min(float(distance_km), MAX_DISTANCE_KM), 2),
        "purpose_match": int(bool(a.purpose) and a.purpose == b.purpose),
        "style_match": style_compatible(a.play_style, b.play_style),
    }
