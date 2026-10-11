"""
Phục vụ mô hình ghép cặp người chơi (Random Forest).

Mô hình nhận 5 đặc trưng định nghĩa trong app.ml.features. Nếu không nạp được file mô hình hoặc
mô hình được huấn luyện với bộ đặc trưng khác, dịch vụ báo "chưa sẵn sàng" và KHÔNG tự thay bằng
công thức ước lượng nào khác, để con số hiển thị luôn đúng là của mô hình.
"""
import hashlib
import hmac
import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import joblib
import pandas as pd
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.matching_policy import RECOMMEND_MIN_COMPATIBILITY
from app.ml.features import (
    AVAILABILITY_SLOTS,
    FEATURE_NAMES,
    PLAY_STYLES,
    PURPOSES,
    ProfileView,
    haversine_km,
    pair_features,
)
from app.models.match import Match
from app.models.ml import PairFeedback
from app.models.user import PlayerProfile, User, UserRole

logger = logging.getLogger("pickleball.ml")

ML_DIR = Path(__file__).resolve().parents[1] / "ml"
MODEL_PATH = ML_DIR / "match_rf_model.pkl"
META_PATH = ML_DIR / "model_meta.json"

MAX_CANDIDATES = 300
LEVEL_WINDOW = 1.5  # chỉ xét ứng viên chênh trình độ trong khoảng này


class MatchPredictor:
    def __init__(self):
        self.model = None
        self.meta: dict = {}
        self.error: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        self.model, self.meta, self.error = None, {}, None
        if not MODEL_PATH.exists():
            self.error = "Chưa có file mô hình. Chạy: python manage.py train-model"
            return
        try:
            model = joblib.load(MODEL_PATH)
            meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
        except Exception as exc:
            self.error = f"Không nạp được mô hình ({exc.__class__.__name__}). Hãy huấn luyện lại với phiên bản thư viện hiện tại."
            logger.warning("Không nạp được mô hình ghép cặp: %s", exc)
            return
        trained_features = list(getattr(model, "feature_names_in_", meta.get("features", [])))
        if trained_features != FEATURE_NAMES:
            self.error = "Mô hình hiện có được huấn luyện với bộ đặc trưng khác. Hãy huấn luyện lại."
            return
        self.model, self.meta = model, meta

    @property
    def available(self) -> bool:
        return self.model is not None

    def info(self) -> dict:
        return {
            "available": self.available,
            "error": self.error,
            "algorithm": self.meta.get("model", "RandomForestClassifier"),
            "features": FEATURE_NAMES,
            "data_source": self.meta.get("data_source"),
            "n_samples": self.meta.get("n_samples"),
            "n_raters": self.meta.get("n_raters"),
            "evaluation_protocol": self.meta.get("evaluation_protocol"),
            "metrics": self.meta.get("metrics"),
            "baselines": self.meta.get("baselines"),
            "feature_importances": self.meta.get("feature_importances"),
            "trained_at": self.meta.get("trained_at"),
            "recommend_threshold": RECOMMEND_MIN_COMPATIBILITY,
        }

    def predict_proba(self, rows: Sequence[Dict[str, float]]) -> List[float]:
        """Xác suất 'phù hợp' cho nhiều cặp trong MỘT lần gọi mô hình."""
        if not rows:
            return []
        if not self.available:
            raise RuntimeError(self.error or "Mô hình chưa sẵn sàng")
        frame = pd.DataFrame(list(rows), columns=FEATURE_NAMES)
        return [float(p) for p in self.model.predict_proba(frame)[:, 1]]


match_predictor = MatchPredictor()


def _display_name(user: User) -> str:
    profile = user.player_profile
    return profile.full_name if profile and profile.full_name else f"Người chơi #{user.id}"


# ---------------------------------------------------------------------------
# Gợi ý người chơi
# ---------------------------------------------------------------------------
def recommend_partners(
    db: Session,
    user: User,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius_km: Optional[float] = None,
    limit: int = 8,
) -> dict:
    me = ProfileView.from_profile(user.player_profile)
    if latitude is not None and longitude is not None:
        me.latitude, me.longitude = latitude, longitude

    result = {"model": match_predictor.info(), "missing_profile_fields": me.missing_fields(), "items": []}
    if not match_predictor.available or me.skill_level is None:
        return result

    candidates = (
        db.query(User)
        .join(PlayerProfile, PlayerProfile.user_id == User.id)
        .options(joinedload(User.player_profile))
        .filter(
            User.id != user.id,
            User.role == UserRole.PLAYER.value,
            User.is_active.is_(True),
            PlayerProfile.skill_level.isnot(None),
            PlayerProfile.skill_level.between(me.skill_level - LEVEL_WINDOW, me.skill_level + LEVEL_WINDOW),
        )
        .order_by(User.id.asc())
        .limit(MAX_CANDIDATES)
        .all()
    )

    rows, kept = [], []
    for candidate in candidates:
        other = ProfileView.from_profile(candidate.player_profile)
        features = pair_features(me, other)
        if features is None:
            continue
        has_distance = None not in (me.latitude, me.longitude, other.latitude, other.longitude)
        if radius_km is not None and has_distance and features["distance_km"] > radius_km:
            continue
        rows.append(features)
        kept.append((candidate, other, has_distance))

    probabilities = match_predictor.predict_proba(rows)
    items = []
    for (candidate, other, has_distance), features, probability in zip(kept, rows, probabilities):
        items.append({
            "user_id": candidate.id,
            "full_name": _display_name(candidate),
            "skill_level": other.skill_level,
            "play_style": other.play_style,
            "purpose": other.purpose,
            "distance_km": features["distance_km"] if has_distance else None,
            "shared_slots": len(set(me.availability) & set(other.availability)),
            "probability": round(probability * 100, 1),
            "features": features,
        })
    # Xác suất bằng nhau thì ưu tiên người sát trình độ hơn, rồi tới người ở gần hơn
    items.sort(key=lambda item: (-item["probability"], item["features"]["level_diff"], item["features"]["distance_km"]))
    result["items"] = items[:limit]
    return result


# ---------------------------------------------------------------------------
# Độ phù hợp với phòng đấu
# ---------------------------------------------------------------------------
def match_compatibility(
    user: User, matches: Sequence[Match], latitude: Optional[float] = None, longitude: Optional[float] = None
) -> Dict[int, float]:
    """
    Độ phù hợp (0-100) của người dùng với từng phòng đấu = trung bình xác suất mô hình giữa người dùng
    và các thành viên hiện có. Khoảng cách tính từ vị trí người dùng tới SÂN của phòng đấu.
    """
    me = ProfileView.from_profile(user.player_profile)
    if latitude is not None and longitude is not None:
        me.latitude, me.longitude = latitude, longitude
    if not match_predictor.available or me.skill_level is None:
        return {}

    rows: List[Dict[str, float]] = []
    owners: List[int] = []
    for match in matches:
        venue = match.venue
        distance = None
        if venue and None not in (me.latitude, me.longitude, venue.latitude, venue.longitude):
            distance = haversine_km(me.latitude, me.longitude, venue.latitude, venue.longitude)
        for participant in match.participants:
            if participant.user_id == user.id or participant.user is None:
                continue
            features = pair_features(me, ProfileView.from_profile(participant.user.player_profile), distance_km=distance)
            if features is not None:
                rows.append(features)
                owners.append(match.id)

    scores: Dict[int, List[float]] = {}
    for match_id, probability in zip(owners, match_predictor.predict_proba(rows)):
        scores.setdefault(match_id, []).append(probability)
    return {match_id: round(sum(values) / len(values) * 100, 1) for match_id, values in scores.items()}


def missing_profile_fields(user: User) -> List[str]:
    """Các mục hồ sơ mà mô hình ghép cặp cần nhưng người chơi chưa khai."""
    return ProfileView.from_profile(user.player_profile).missing_fields()


def predict_pair(user_a: User, user_b: User) -> dict:
    features = pair_features(ProfileView.from_profile(user_a.player_profile), ProfileView.from_profile(user_b.player_profile))
    if features is None or not match_predictor.available:
        return {"model_available": match_predictor.available, "success_probability": None,
                "is_match_recommended": None, "features_used": features or {}}
    probability = match_predictor.predict_proba([features])[0]
    return {"model_available": True, "success_probability": probability,
            "is_match_recommended": probability >= 0.5, "features_used": features}


# ---------------------------------------------------------------------------
# Khảo sát thu nhãn thật
# ---------------------------------------------------------------------------
def _sign(features: Dict[str, float]) -> str:
    """Chữ ký để người trả lời không tự sửa đặc trưng của cặp được hỏi."""
    # Chuẩn hóa về 3 chữ số thập phân để 1 và 1.0 (sau khi đi qua JSON) cho cùng một chữ ký
    canonical = "|".join(f"{name}={float(features[name]):.3f}" for name in FEATURE_NAMES)
    return hmac.new(settings.SECRET_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def generate_survey_pairs(user: User, count: int = 10) -> Tuple[List[dict], List[str]]:
    """
    Sinh các hồ sơ ứng viên GIẢ ĐỊNH xoay quanh hồ sơ thật của người trả lời, trải đều các mức
    chênh trình độ, khoảng cách và độ trùng lịch, để người chơi trả lời có muốn ghép hay không.
    """
    me = ProfileView.from_profile(user.player_profile)
    if me.skill_level is None:
        return [], me.missing_fields()

    rng = random.Random()
    my_slots = me.availability or rng.sample(AVAILABILITY_SLOTS, 6)
    pairs = []
    for _ in range(count):
        level = min(8.0, max(1.0, me.skill_level + rng.choice([-2.0, -1.5, -1.0, -0.5, 0.0, 0.0, 0.5, 1.0, 1.5, 2.0])))
        shared = rng.sample(my_slots, rng.randint(0, len(my_slots)))
        extra = rng.sample([s for s in AVAILABILITY_SLOTS if s not in my_slots], rng.randint(0, 5))
        candidate = ProfileView(
            skill_level=level,
            availability=shared + extra,
            purpose=rng.choice(PURPOSES),
            play_style=rng.choice(PLAY_STYLES),
        )
        distance = round(rng.choice([1, 2, 3, 5, 8, 12, 18, 25, 35]) * rng.uniform(0.8, 1.2), 1)
        viewer = ProfileView(me.skill_level, None, None, my_slots, me.purpose, me.play_style)
        features = pair_features(viewer, candidate, distance_km=distance)
        pairs.append({
            "candidate": {
                "skill_level": level,
                "distance_km": distance,
                "shared_slots": len(shared),
                "availability": candidate.availability,
                "purpose": candidate.purpose,
                "play_style": candidate.play_style,
            },
            "features": features,
            "signature": _sign(features),
        })
    return pairs, me.missing_fields()


def save_survey_answers(db: Session, user: User, answers: Sequence) -> int:
    saved = 0
    for answer in answers:
        features = {name: answer.features.get(name) for name in FEATURE_NAMES}
        if any(v is None for v in features.values()) or not hmac.compare_digest(_sign(features), answer.signature):
            continue  # bỏ qua câu trả lời có đặc trưng bị sửa
        db.add(PairFeedback(
            rater_id=user.id,
            source="survey",
            label=int(bool(answer.label)),
            level_diff=float(features["level_diff"]),
            distance_km=float(features["distance_km"]),
            availability_overlap=float(features["availability_overlap"]),
            purpose_match=int(features["purpose_match"]),
            style_match=int(features["style_match"]),
        ))
        saved += 1
    db.commit()
    return saved


def feedback_summary(db: Session) -> dict:
    from sqlalchemy import func

    total, positive, raters = db.query(
        func.count(PairFeedback.id), func.coalesce(func.sum(PairFeedback.label), 0), func.count(func.distinct(PairFeedback.rater_id))
    ).one()
    return {"labels": int(total), "positive": int(positive), "raters": int(raters)}
