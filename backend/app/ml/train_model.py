"""
Huấn luyện mô hình ghép cặp người chơi (Random Forest) và lưu kèm file mô tả.

    python -m app.ml.train_model              # huấn luyện, đánh giá và lưu match_rf_model.pkl + model_meta.json
    python -m app.ml.train_model --report     # chỉ in bảng đánh giá, không ghi file
    python -m app.ml.train_model --synthetic  # buộc dùng dữ liệu tổng hợp (bỏ qua dữ liệu khảo sát)

Nguồn dữ liệu, theo thứ tự ưu tiên:
1. "survey": câu trả lời khảo sát thật trong bảng pair_feedback, khi có từ MIN_REAL_SAMPLES nhãn trở lên.
2. "simulated": các dòng của bảng pair_feedback khi phần lớn là PHIẾU MÔ PHỎNG nạp sẵn
   (python manage.py seed --feedback) - dữ liệu nằm trong CSDL, nhãn sinh từ quy tắc viết tay có cộng nhiễu.
3. "synthetic_prior": dữ liệu tổng hợp sinh trong bộ nhớ từ cùng quy tắc đó, dùng khi CSDL chưa có đủ dòng.
Dữ liệu lấy từ CSDL (1 và 2) được đánh giá bằng GroupKFold theo người trả lời, để phiếu của cùng một người không
nằm ở cả hai phía. Với nguồn 2 và 3, độ chính xác chỉ cho biết mô hình học lại quy tắc tốt đến đâu, KHÔNG chứng
minh chất lượng ghép cặp ngoài thực tế; quy tắc gốc (không nhiễu) luôn được in ra làm mốc trần so sánh.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupKFold, train_test_split

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from app.ml.features import FEATURE_NAMES, MAX_DISTANCE_KM  # noqa: E402
from app.models.ml import SIMULATED_SOURCE  # noqa: E402

ML_DIR = Path(__file__).resolve().parent
MODEL_PATH = ML_DIR / "match_rf_model.pkl"
META_PATH = ML_DIR / "model_meta.json"

MIN_REAL_SAMPLES = 300
SYNTHETIC_SAMPLES = 60000
RANDOM_STATE = 42
LABEL_NOISE_SD = 0.08   # độ lệch chuẩn của nhiễu cộng vào điểm quy tắc khi sinh nhãn mô phỏng


# ---------------------------------------------------------------------------
# Dữ liệu
# ---------------------------------------------------------------------------
def synthetic_rule_score(df: pd.DataFrame) -> np.ndarray:
    """Quy tắc viết tay dùng để gán nhãn dữ liệu tổng hợp (chưa cộng nhiễu). Nhãn = 1 khi điểm >= 0.5."""
    level, dist = df["level_diff"].to_numpy(), df["distance_km"].to_numpy()
    score = np.full(len(df), 0.50)
    score += np.select([level <= 0.25, level <= 0.5, level <= 1.0], [0.30, 0.18, -0.10], default=-0.38)
    score += np.select([dist <= 3, dist <= 8, dist <= 15], [0.10, 0.04, -0.06], default=-0.18)
    score += 0.25 * (df["availability_overlap"].to_numpy() - 0.3)
    score += np.where(df["purpose_match"].to_numpy() == 1, 0.08, -0.06)
    score += np.where(df["style_match"].to_numpy() == 1, 0.05, -0.03)
    return score


def noisy_rule_labels(features: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Nhãn mô phỏng cho các cặp: điểm của quy tắc viết tay cộng nhiễu Gauss, 1 khi đạt từ 0.5."""
    noisy = synthetic_rule_score(features) + rng.normal(0, LABEL_NOISE_SD, len(features))
    return (noisy >= 0.5).astype(int)


def generate_synthetic_pairs(n: int = SYNTHETIC_SAMPLES, seed: int = RANDOM_STATE) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    level_a = np.clip(np.round(rng.normal(3.5, 0.8, n) * 2) / 2, 2.0, 5.5)
    level_b = np.clip(np.round(rng.normal(3.5, 0.8, n) * 2) / 2, 2.0, 5.5)
    overlap = rng.beta(1.2, 2.5, n)
    overlap[rng.random(n) < 0.2] = 0.0
    df = pd.DataFrame({
        "level_diff": np.abs(level_a - level_b),
        "distance_km": np.clip(rng.exponential(8.0, n), 0.2, MAX_DISTANCE_KM).round(2),
        "availability_overlap": overlap.round(3),
        "purpose_match": (rng.random(n) < 0.40).astype(int),
        "style_match": (rng.random(n) < 0.45).astype(int),
    })
    df["label"] = noisy_rule_labels(df, rng)
    return df


def load_real_feedback() -> pd.DataFrame:
    """Mọi dòng của bảng pair_feedback (khảo sát thật lẫn phiếu mô phỏng). Bảng rỗng nếu chưa kết nối được CSDL."""
    columns = FEATURE_NAMES + ["label", "rater_id", "source"]
    try:
        from app.db.database import engine

        return pd.read_sql(f"SELECT {', '.join(columns)} FROM pair_feedback", engine)
    except Exception as exc:
        print(f"(Không đọc được dữ liệu khảo sát: {exc.__class__.__name__})")
        return pd.DataFrame(columns=columns)


# ---------------------------------------------------------------------------
# Đánh giá
# ---------------------------------------------------------------------------
def metrics(y_true, y_pred, y_prob=None) -> Dict[str, float]:
    result = {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
    }
    if y_prob is not None and len(set(y_true)) > 1:
        result["roc_auc"] = round(float(roc_auc_score(y_true, y_prob)), 4)
        result["brier"] = round(float(brier_score_loss(y_true, y_prob)), 4)
    return result


def build_model(n_samples: int) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=20 if n_samples >= 5000 else 5,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )


def evaluate_split(X_train, y_train, X_test, y_test, include_rule: bool) -> Dict[str, Dict[str, float]]:
    """So sánh Random Forest với các mốc: đoán theo lớp đa số, luật ngưỡng trình độ, hồi quy logistic."""
    report = {}
    majority = DummyClassifier(strategy="most_frequent").fit(X_train, y_train)
    report["Đoán theo lớp đa số"] = metrics(y_test, majority.predict(X_test))
    report["Luật: chênh trình độ <= 0.5"] = metrics(y_test, (X_test["level_diff"] <= 0.5).astype(int))
    logistic = LogisticRegression(max_iter=1000).fit(X_train, y_train)
    report["Hồi quy logistic"] = metrics(y_test, logistic.predict(X_test), logistic.predict_proba(X_test)[:, 1])
    forest = build_model(len(X_train)).fit(X_train, y_train)
    report["Random Forest"] = metrics(y_test, forest.predict(X_test), forest.predict_proba(X_test)[:, 1])
    if include_rule:
        rule = (synthetic_rule_score(X_test) >= 0.5).astype(int)
        report["Quy tắc sinh nhãn (không nhiễu, mốc trần)"] = metrics(y_test, rule)
    return report


def average_reports(reports) -> Dict[str, Dict[str, float]]:
    merged: Dict[str, Dict[str, float]] = {}
    for name in reports[0]:
        keys = reports[0][name].keys()
        merged[name] = {k: round(float(np.mean([r[name][k] for r in reports if k in r[name]])), 4) for k in keys}
    return merged


def print_report(report: Dict[str, Dict[str, float]]) -> None:
    print(f"{'Phương pháp':<44}{'Accuracy':>9}{'Precision':>10}{'Recall':>8}{'F1':>8}{'ROC-AUC':>9}")
    print("-" * 88)
    for name, m in report.items():
        auc = f"{m['roc_auc']:.4f}" if "roc_auc" in m else "   -"
        print(f"{name:<44}{m['accuracy']:>9.4f}{m['precision']:>10.4f}{m['recall']:>8.4f}{m['f1']:>8.4f}{auc:>9}")


# ---------------------------------------------------------------------------
# Huấn luyện
# ---------------------------------------------------------------------------
def choose_dataset(force_synthetic: bool) -> Tuple[pd.DataFrame, str, Optional[pd.Series]]:
    """
    Trả về (dữ liệu, nguồn, người trả lời của từng dòng). Số dòng thật và mô phỏng nằm trong data.attrs.
    Nhãn khảo sát thật luôn được ưu tiên: đủ MIN_REAL_SAMPLES nhãn thật thì phiếu mô phỏng bị bỏ ra ngoài.
    """
    feedback = pd.DataFrame() if force_synthetic else load_real_feedback()
    if len(feedback):
        sources = feedback["source"] if "source" in feedback else pd.Series("survey", index=feedback.index)
        real = feedback[sources != SIMULATED_SOURCE]
        if len(real) >= MIN_REAL_SAMPLES and real["label"].nunique() == 2:
            chosen, name = real, "survey"
        elif len(feedback) >= MIN_REAL_SAMPLES and feedback["label"].nunique() == 2:
            chosen, name = feedback, "simulated"
        else:
            chosen, name = None, ""
            print(f"Mới có {len(feedback)} nhãn trong CSDL (cần >= {MIN_REAL_SAMPLES}); tạm dùng dữ liệu tổng hợp khởi tạo.")
        if chosen is not None:
            data = chosen[FEATURE_NAMES + ["label"]].astype(float)
            n_survey = int(len(real)) if name == "simulated" else int(len(chosen))
            data.attrs.update(n_survey=n_survey, n_simulated=int(len(chosen)) - n_survey)
            return data, name, chosen["rater_id"]
    return generate_synthetic_pairs(SYNTHETIC_SAMPLES), "synthetic_prior", None


def train(report_only: bool = False, force_synthetic: bool = False) -> dict:
    data, source, groups = choose_dataset(force_synthetic)
    X, y = data[FEATURE_NAMES], data["label"].astype(int)

    print("=" * 88)
    print(f"Nguồn dữ liệu: {source} | {len(data):,} cặp | tỷ lệ nhãn 'muốn ghép': {y.mean():.1%}")
    if source == "synthetic_prior":
        print("LƯU Ý: nhãn sinh từ quy tắc viết tay + nhiễu; các số dưới đây không phản ánh hành vi người chơi thật.")
    elif source == "simulated":
        print(f"LƯU Ý: {data.attrs.get('n_simulated', 0):,} dòng là PHIẾU MÔ PHỎNG nạp trong CSDL (nhãn sinh từ quy tắc "
              "viết tay + nhiễu); các số dưới đây không phản ánh hành vi người chơi thật.")
    print("=" * 88)

    if source in ("survey", "simulated"):
        n_groups = groups.nunique()
        folds = GroupKFold(n_splits=min(5, n_groups)) if n_groups >= 2 else None
        if folds is None:
            raise SystemExit("Cần nhãn từ ít nhất 2 người trả lời để đánh giá theo nhóm.")
        report = average_reports([
            evaluate_split(X.iloc[tr], y.iloc[tr], X.iloc[te], y.iloc[te], include_rule=source == "simulated")
            for tr, te in folds.split(X, y, groups)
        ])
        protocol = f"GroupKFold {folds.n_splits} phần theo người trả lời ({n_groups} người)"
    else:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)
        report = evaluate_split(X_train, y_train, X_test, y_test, include_rule=True)
        protocol = "Tách ngẫu nhiên 80/20 có phân tầng"

    print(f"Cách đánh giá: {protocol}\n")
    print_report(report)

    model = build_model(len(X)).fit(X, y)
    importances = {f: round(float(v), 4) for f, v in zip(FEATURE_NAMES, model.feature_importances_)}
    print("\nMức đóng góp của đặc trưng:", importances)

    meta = {
        "model": "RandomForestClassifier",
        "features": FEATURE_NAMES,
        "data_source": source,
        "n_samples": int(len(data)),
        "n_raters": int(groups.nunique()) if groups is not None else 0,
        "n_survey": int(data.attrs.get("n_survey", 0)),
        "n_simulated": int(data.attrs.get("n_simulated", 0)),
        "positive_rate": round(float(y.mean()), 4),
        "evaluation_protocol": protocol,
        "metrics": report["Random Forest"],
        "baselines": {k: v for k, v in report.items() if k != "Random Forest"},
        "feature_importances": importances,
        "sklearn_version": sklearn.__version__,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if not report_only:
        joblib.dump(model, MODEL_PATH, compress=3)
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nĐã lưu {MODEL_PATH.name} ({MODEL_PATH.stat().st_size / 1024:.0f} KB) và {META_PATH.name}")
    return meta


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Huấn luyện mô hình ghép cặp người chơi")
    parser.add_argument("--report", action="store_true", help="Chỉ in bảng đánh giá, không ghi file mô hình")
    parser.add_argument("--synthetic", action="store_true", help="Buộc dùng dữ liệu tổng hợp khởi tạo")
    args = parser.parse_args()
    train(report_only=args.report, force_synthetic=args.synthetic)
