"""Mô hình ghép cặp: đặc trưng dùng chung, huấn luyện/đánh giá, phục vụ theo lô và khảo sát thu nhãn."""
import json

import joblib
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from app.ml import features as F
from app.ml import train_model
from app.ml.features import FEATURE_NAMES, ProfileView, pair_features
from app.models.ml import PairFeedback
from app.services import ml_service
from app.services.ml_service import match_predictor
from helpers import auth, make_user

ML = "/api/v1/ml"
RULE_CEILING = "Quy tắc sinh nhãn (không nhiễu, mốc trần)"


def view(**kwargs) -> ProfileView:
    return ProfileView(**{"skill_level": 3.5, **kwargs})


# ---------------------------------------------------------------------------
# Đặc trưng
# ---------------------------------------------------------------------------
def test_pair_features_are_symmetric_and_use_the_four_documented_features():
    a = view(latitude=10.78, longitude=106.70, purpose="practice", play_style="Offensive")
    b = view(skill_level=4.0, latitude=10.80, longitude=106.72, purpose="practice", play_style="All-Round")
    ab, ba = pair_features(a, b), pair_features(b, a)
    assert ab == ba and list(ab) == FEATURE_NAMES == ["level_diff", "distance_km", "purpose_match", "style_match"]
    assert ab == {"level_diff": 0.5, "distance_km": pytest.approx(3.11, abs=0.05), "purpose_match": 1, "style_match": 1}


def test_missing_data_handling():
    assert pair_features(ProfileView(), view()) is None                     # chưa khai trình độ thì không ước lượng
    unknown = pair_features(view(), view())
    assert unknown["distance_km"] == F.UNKNOWN_DISTANCE_KM
    assert (unknown["purpose_match"], unknown["style_match"]) == (0, 0)
    far = pair_features(view(latitude=10.78, longitude=106.70), view(latitude=21.03, longitude=105.85))
    assert far["distance_km"] == F.MAX_DISTANCE_KM
    assert pair_features(view(), view(), distance_km=7.25)["distance_km"] == 7.25
    assert view().missing_fields() == ["location", "purpose", "play_style"]


@pytest.mark.parametrize("raw, canonical", [
    ("Tấn công (Aggressive)", "Offensive"), ("Phòng thủ - Phản công (Dinking)", "Dinking & Control"),
    ("Toàn diện (All-Around)", "All-Round"), ("Giao bóng & Bắt lưới", "Serve & Volley"),
    ("Dinking & Control", "Dinking & Control"), ("defensive", "Defensive"), ("gì đó", None), (None, None),
])
def test_legacy_play_style_labels_are_canonicalised(raw, canonical):
    assert F.canonical_style(raw) == canonical


def test_profile_view_ignores_unknown_values(db):
    user = make_user(db, skill_level=3.0, purpose="hacking", play_style="Tấn công")
    profile = ProfileView.from_profile(user.player_profile)
    assert profile.purpose is None and profile.play_style == "Offensive"


# ---------------------------------------------------------------------------
# Huấn luyện và đánh giá
# ---------------------------------------------------------------------------
def test_synthetic_prior_is_reproducible_and_balanced():
    first, second = train_model.generate_synthetic_pairs(2000, seed=7), train_model.generate_synthetic_pairs(2000, seed=7)
    assert first.equals(second) and list(first.columns) == FEATURE_NAMES + ["label"]
    assert 0.35 < first["label"].mean() < 0.65
    assert first["distance_km"].between(0, F.MAX_DISTANCE_KM).all()


def test_evaluation_reports_baselines_next_to_the_forest():
    data = train_model.generate_synthetic_pairs(6000, seed=1)
    train, test = data.iloc[:4800], data.iloc[4800:]
    report = train_model.evaluate_split(
        train[FEATURE_NAMES], train["label"], test[FEATURE_NAMES], test["label"], include_rule=True)

    forest = report["Random Forest"]["accuracy"]
    assert forest > report["Đoán theo lớp đa số"]["accuracy"] + 0.2
    assert forest >= report["Luật: chênh trình độ <= 0.5"]["accuracy"]
    assert forest <= report[RULE_CEILING]["accuracy"] + 0.02   # mô hình không thể giỏi hơn chính quy tắc sinh ra nhãn
    assert {"roc_auc", "brier"} <= set(report["Random Forest"])


def test_training_prefers_real_survey_labels_and_evaluates_by_rater(db, monkeypatch):
    raters = [make_user(db, skill_level=3.5).id for _ in range(6)]
    pairs = train_model.generate_synthetic_pairs(360, seed=3)
    db.add_all([
        PairFeedback(rater_id=raters[i % 6], label=int(row.label), level_diff=float(row.level_diff),
                     distance_km=float(row.distance_km), purpose_match=int(row.purpose_match), style_match=int(row.style_match))
        for i, row in enumerate(pairs.itertuples())
    ])
    db.commit()

    meta = train_model.train(report_only=True)
    assert (meta["data_source"], meta["n_samples"], meta["n_raters"]) == ("survey", 360, 6)
    assert "GroupKFold" in meta["evaluation_protocol"] and RULE_CEILING not in meta["baselines"]

    monkeypatch.setattr(train_model, "SYNTHETIC_SAMPLES", 4000)
    forced = train_model.train(report_only=True, force_synthetic=True)
    assert (forced["data_source"], forced["n_samples"], forced["n_raters"]) == ("synthetic_prior", 4000, 0)
    assert RULE_CEILING in forced["baselines"]


def test_too_few_survey_labels_fall_back_to_the_synthetic_prior(db, monkeypatch):
    rater = make_user(db, skill_level=3.5)
    db.add(PairFeedback(rater_id=rater.id, label=1, level_diff=0, distance_km=1, purpose_match=1, style_match=1))
    db.commit()
    monkeypatch.setattr(train_model, "SYNTHETIC_SAMPLES", 3000)
    data, source, groups = train_model.choose_dataset(force_synthetic=False)
    assert source == "synthetic_prior" and groups is None and len(data) == 3000


def _load_simulated_feedback(db, players: int = 3, per_player: int = 120):
    """Tạo vài tài khoản demo rồi nạp phiếu mô phỏng cho họ, đúng như `python manage.py seed --feedback`."""
    from scripts import seed

    raters = [make_user(db, "PLAYER", persona.email, skill_level=persona.skill_level) for persona in seed.PLAYERS[:players]]
    return raters, seed.seed_simulated_feedback(db, per_player=per_player)


def test_simulated_feedback_is_stored_in_the_database_and_marked_as_simulated(db):
    from scripts import seed

    raters, added = _load_simulated_feedback(db)
    assert added == 360
    rows = db.query(PairFeedback).all()
    assert {r.source for r in rows} == {"simulated"} and {r.rater_id for r in rows} == {u.id for u in raters}
    assert {r.label for r in rows} == {0, 1}
    assert all(r.distance_km > 0 and r.level_diff >= 0 for r in rows)
    # cả bốn đặc trưng đều biến thiên, không đặc trưng nào bị đứng yên
    assert {r.purpose_match for r in rows} == {0, 1} == {r.style_match for r in rows}
    assert len({r.level_diff for r in rows}) >= 4 and len({round(r.distance_km) for r in rows}) >= 4

    assert seed.seed_simulated_feedback(db, per_player=120) == 0                     # chạy lại không nạp trùng
    assert db.query(PairFeedback).count() == 360
    # phiếu mô phỏng không được tính là nhãn khảo sát thật
    assert ml_service.feedback_summary(db) == {"labels": 0, "positive": 0, "raters": 0, "simulated": 360}


def test_simulated_feedback_is_the_same_on_every_installation(db):
    _load_simulated_feedback(db)
    first = [(r.rater_id, r.level_diff, r.distance_km, r.purpose_match, r.style_match, r.label)
             for r in db.query(PairFeedback).order_by(PairFeedback.id)]
    db.query(PairFeedback).delete()
    db.commit()
    from scripts import seed

    seed.seed_simulated_feedback(db, per_player=120)
    second = [(r.rater_id, r.level_diff, r.distance_km, r.purpose_match, r.style_match, r.label)
              for r in db.query(PairFeedback).order_by(PairFeedback.id)]
    assert first == second


def test_training_reads_simulated_feedback_from_the_database_and_says_so(db):
    _load_simulated_feedback(db)
    data, source, groups = train_model.choose_dataset(force_synthetic=False)
    assert (source, len(data), groups.nunique()) == ("simulated", 360, 3)

    meta = train_model.train(report_only=True)
    assert (meta["data_source"], meta["n_samples"], meta["n_raters"]) == ("simulated", 360, 3)
    assert (meta["n_simulated"], meta["n_survey"]) == (360, 0)
    assert "GroupKFold" in meta["evaluation_protocol"] and RULE_CEILING in meta["baselines"]


def test_real_survey_answers_replace_simulated_ones_once_there_are_enough(db):
    raters, _ = _load_simulated_feedback(db)
    real = train_model.generate_synthetic_pairs(300, seed=5)
    db.add_all([
        PairFeedback(rater_id=raters[i % 3].id, label=int(row.label), level_diff=float(row.level_diff),
                     distance_km=float(row.distance_km), purpose_match=int(row.purpose_match), style_match=int(row.style_match))
        for i, row in enumerate(real.itertuples())
    ])
    db.commit()

    data, source, _ = train_model.choose_dataset(force_synthetic=False)
    assert (source, len(data)) == ("survey", 300)
    assert (data.attrs["n_survey"], data.attrs["n_simulated"]) == (300, 0)
    assert ml_service.feedback_summary(db)["labels"] == 300 and ml_service.feedback_summary(db)["simulated"] == 360


# ---------------------------------------------------------------------------
# Phục vụ mô hình
# ---------------------------------------------------------------------------
def test_shipped_model_matches_the_feature_module_and_its_metadata():
    assert match_predictor.available, match_predictor.error
    info = match_predictor.info()
    assert info["features"] == FEATURE_NAMES and list(match_predictor.model.feature_names_in_) == FEATURE_NAMES
    assert info["data_source"] in ("synthetic_prior", "simulated", "survey")
    assert info["metrics"]["accuracy"] > 0.8 and info["baselines"]


def test_batch_prediction_equals_one_by_one_and_follows_common_sense():
    rows = [
        {"level_diff": 0.0, "distance_km": 2.0, "purpose_match": 1, "style_match": 1},
        {"level_diff": 0.5, "distance_km": 12.0, "purpose_match": 0, "style_match": 0},
        {"level_diff": 2.5, "distance_km": 30.0, "purpose_match": 0, "style_match": 0},
    ]
    batch = match_predictor.predict_proba(rows)
    assert batch == pytest.approx([match_predictor.predict_proba([row])[0] for row in rows])
    assert batch[0] > batch[1] > batch[2] and batch[0] > 0.9 and batch[2] < 0.1
    assert match_predictor.predict_proba([]) == []


def test_a_model_trained_on_other_features_is_reported_unavailable_without_a_fake_fallback(client, db, tmp_path, monkeypatch):
    stale = RandomForestClassifier(n_estimators=3, random_state=0).fit(
        pd.DataFrame({"level_diff": [0, 1, 2, 3], "age_diff": [1, 2, 3, 4]}), [1, 1, 0, 0])
    path = tmp_path / "match_rf_model.pkl"
    joblib.dump(stale, path)
    monkeypatch.setattr(ml_service, "MODEL_PATH", path)
    monkeypatch.setattr(ml_service, "META_PATH", tmp_path / "model_meta.json")
    match_predictor.reload()
    try:
        assert not match_predictor.available and "đặc trưng" in match_predictor.error
        me, other = make_user(db, skill_level=3.5), make_user(db, skill_level=3.5)
        partners = client.get(f"{ML}/recommend-partners", headers=auth(me)).json()
        assert partners["items"] == [] and partners["model"]["available"] is False
        predicted = client.post(f"{ML}/predict-match", json={"user_b_id": other.id}, headers=auth(me)).json()
        assert predicted["model_available"] is False and predicted["success_probability"] is None

        monkeypatch.setattr(ml_service, "MODEL_PATH", tmp_path / "missing.pkl")
        match_predictor.reload()
        assert not match_predictor.available and "train-model" in match_predictor.error
    finally:
        monkeypatch.undo()
        match_predictor.reload()
    assert match_predictor.available


# ---------------------------------------------------------------------------
# API gợi ý người chơi
# ---------------------------------------------------------------------------
def test_recommend_partners_ranks_real_candidates_without_contact_details(client, db):
    common = dict(latitude=10.78, longitude=106.70, purpose="recreational")
    me = make_user(db, skill_level=3.5, play_style="Offensive", **common)
    twin = make_user(db, full_name="Bạn Hợp", phone="0900111222", skill_level=3.5, play_style="Offensive", **common)
    weaker = make_user(db, full_name="Bạn Lệch", skill_level=2.5, play_style="Defensive", latitude=10.95, longitude=106.90)
    make_user(db, full_name="Quá xa trình", skill_level=5.5)          # ngoài khoảng trình độ xét duyệt
    make_user(db, full_name="Chưa khai trình độ")
    locked = make_user(db, full_name="Bị khóa", skill_level=3.5)
    locked.is_active = False
    db.commit()
    make_user(db, "OWNER")

    body = client.get(f"{ML}/recommend-partners", headers=auth(me)).json()
    assert body["missing_profile_fields"] == [] and body["model"]["available"] is True
    assert [item["full_name"] for item in body["items"]] == ["Bạn Hợp", "Bạn Lệch"]
    best, worst = body["items"]
    assert best["user_id"] == twin.id and best["probability"] > worst["probability"]
    assert best["distance_km"] == 0 and list(best["features"]) == FEATURE_NAMES
    assert worst["user_id"] == weaker.id
    dump = json.dumps(body["items"])
    assert "@" not in dump and "0900111222" not in dump

    nearby = client.get(f"{ML}/recommend-partners", headers=auth(me), params={"radius_km": 5}).json()
    assert [item["user_id"] for item in nearby["items"]] == [twin.id]
    assert len(client.get(f"{ML}/recommend-partners", headers=auth(me), params={"limit": 1}).json()["items"]) == 1
    assert client.get(f"{ML}/recommend-partners").status_code == 401


def test_incomplete_profile_is_told_what_is_missing(client, db):
    blank = make_user(db)
    body = client.get(f"{ML}/recommend-partners", headers=auth(blank)).json()
    assert body["items"] == []
    assert body["missing_profile_fields"] == ["skill_level", "location", "purpose", "play_style"]


def test_predict_match_uses_the_callers_own_profile(client, db):
    me, other, third = (make_user(db, skill_level=level) for level in (3.5, 3.5, 6.0))
    request = {"user_a_id": third.id, "user_b_id": other.id}
    mine = client.post(f"{ML}/predict-match", json=request, headers=auth(me)).json()
    assert mine["features_used"]["level_diff"] == 0.0 and mine["is_match_recommended"] is True   # user_a_id bị bỏ qua
    admin = make_user(db, "ADMIN")
    theirs = client.post(f"{ML}/predict-match", json=request, headers=auth(admin)).json()
    assert theirs["features_used"]["level_diff"] == 2.5 and theirs["is_match_recommended"] is False
    assert client.post(f"{ML}/predict-match", json={"user_b_id": 99999}, headers=auth(me)).status_code == 404


# ---------------------------------------------------------------------------
# Khảo sát thu nhãn
# ---------------------------------------------------------------------------
def test_survey_answers_are_stored_only_when_untampered(client, db):
    me = make_user(db, skill_level=3.5, purpose="practice", play_style="Offensive")
    survey = client.get(f"{ML}/survey/pairs", headers=auth(me), params={"count": 4}).json()
    pairs = survey["pairs"]
    assert len(pairs) == 4 and all(list(p["features"]) == FEATURE_NAMES for p in pairs)
    assert all(set(p["candidate"]) == {"skill_level", "distance_km", "purpose", "play_style"} for p in pairs)

    forged = {**pairs[2]["features"], "level_diff": 0.0, "distance_km": 0.1}
    answers = [
        {"features": pairs[0]["features"], "signature": pairs[0]["signature"], "label": True},
        {"features": pairs[1]["features"], "signature": pairs[1]["signature"], "label": False},
        {"features": forged, "signature": pairs[2]["signature"], "label": True},
        {"features": pairs[3]["features"], "signature": "0" * 64, "label": True},
    ]
    assert client.post(f"{ML}/survey/answers", json={"answers": answers}, headers=auth(me)).json() == {"saved": 2}

    rows = db.query(PairFeedback).order_by(PairFeedback.id).all()
    assert [(r.rater_id, r.label, r.source) for r in rows] == [(me.id, 1, "survey"), (me.id, 0, "survey")]
    assert rows[0].level_diff == pairs[0]["features"]["level_diff"]

    assert client.post(f"{ML}/survey/answers", json={"answers": []}, headers=auth(me)).status_code == 422
    assert client.get(f"{ML}/survey/pairs").status_code == 401


def test_survey_needs_a_skill_level(client, db):
    body = client.get(f"{ML}/survey/pairs", headers=auth(make_user(db))).json()
    assert body["pairs"] == [] and "skill_level" in body["missing_profile_fields"]


def test_model_info_shows_survey_progress_to_admin_only(client, db):
    player, admin = make_user(db, skill_level=3.5), make_user(db, "ADMIN")
    db.add(PairFeedback(rater_id=player.id, label=1, level_diff=0, distance_km=1, purpose_match=1, style_match=1))
    db.commit()
    assert client.get(f"{ML}/model-info").status_code == 401
    assert "survey" not in client.get(f"{ML}/model-info", headers=auth(player)).json()
    info = client.get(f"{ML}/model-info", headers=auth(admin)).json()
    assert info["survey"] == {"labels": 1, "positive": 1, "raters": 1, "simulated": 0} and info["available"] is True


def test_model_info_gives_the_recommendation_threshold_and_what_a_player_still_has_to_fill_in(client, db):
    from app.core.matching_policy import RECOMMEND_MIN_COMPATIBILITY

    player = make_user(db, "PLAYER", skill_level=3.5)      # chưa khai vị trí, mục đích, lối đánh
    info = client.get(f"{ML}/model-info", headers=auth(player)).json()
    assert info["recommend_threshold"] == RECOMMEND_MIN_COMPATIBILITY == 70
    assert info["missing_profile_fields"] == ["location", "purpose", "play_style"]

    admin = make_user(db, "ADMIN")
    assert "missing_profile_fields" not in client.get(f"{ML}/model-info", headers=auth(admin)).json()
