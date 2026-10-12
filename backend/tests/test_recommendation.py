"""Gợi ý cụm sân đa tiêu chí: chuẩn hóa từng tiêu chí (theo đơn vị VNĐ thật) và xếp hạng tổng hợp."""
import pytest

from app.core.recommendation_config import WEIGHTS
from app.models.venue import Amenity, Review
from app.services import venue_recommendation_service as rec
from helpers import auth, confirmed_booking, make_user, make_venue

URL = "/api/v1/recommendations/venues"


def recommend(client, user=None, **params):
    response = client.get(URL, params=params, headers=auth(user) if user else {})
    assert response.status_code == 200, response.text
    items = response.json()
    return {item["venue"]["name"]: item for item in items}, [item["venue"]["name"] for item in items]


# ---------------------------------------------------------------------------
# Hàm chuẩn hóa
# ---------------------------------------------------------------------------
def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)


def test_price_score_with_real_vnd_prices_is_not_stuck_at_zero():
    # Lỗi cũ: so giá 150.000đ với mốc 500 nên điểm giá luôn bằng 0
    assert rec.normalize_price(150000, min_price=120000, max_price=200000) == pytest.approx(0.625)
    assert rec.normalize_price(120000, min_price=120000, max_price=200000) == 1.0
    assert rec.normalize_price(200000, min_price=120000, max_price=200000) == 0.0
    assert rec.normalize_price(150000, min_price=150000, max_price=150000) == 1.0


def test_price_score_against_a_budget():
    assert rec.normalize_price(150000, budget=200000) == 1.0
    assert rec.normalize_price(200000, budget=200000) == 1.0
    assert rec.normalize_price(250000, budget=200000) == pytest.approx(0.5)   # vượt 25% ngân sách
    assert rec.normalize_price(300000, budget=200000) == 0.0                  # vượt 50% trở lên
    assert rec.normalize_price(900000, budget=200000) == 0.0


def test_distance_time_and_preference_scores():
    assert rec.normalize_distance(0) == 1.0 and rec.normalize_distance(10) == 0.5
    assert rec.normalize_distance(20) == 0.0 and rec.normalize_distance(80) == 0.0
    assert rec.normalize_distance(None) is None
    assert rec.normalize_time(9, 12) == 0.75 and rec.normalize_time(0, 12) == 0.0 and rec.normalize_time(0, 0) == 0.0
    assert rec.normalize_preference({1, 2, 3}, {2, 3, 9, 10}) == 0.5
    assert rec.normalize_preference({1}, set()) is None


def test_bayesian_rating_shrinks_small_samples_towards_the_prior():
    assert rec.bayesian_rating(0, None, 4.0) == 4.0
    assert rec.bayesian_rating(1, 5.0, 4.0) == pytest.approx(4.1667, abs=1e-3)   # một đánh giá 5 sao chưa đủ thành 5.0
    assert rec.bayesian_rating(1, 1.0, 4.0) == pytest.approx(3.5)
    assert rec.bayesian_rating(200, 4.8, 4.0) == pytest.approx(4.78, abs=0.01)   # nhiều đánh giá thì gần điểm thật


def test_missing_criteria_are_dropped_and_weights_renormalised():
    full = {"distance": 1.0, "price": 0.0, "time": 1.0, "rating": 0.5, "preference": 1.0}
    assert rec.weighted_score(full) == pytest.approx(0.30 + 0.20 + 0.075 + 0.10)
    partial = {"distance": None, "price": 1.0, "time": 1.0, "rating": 1.0, "preference": None}
    assert rec.weighted_score(partial) == pytest.approx(1.0)   # không bị trừ điểm vì tiêu chí không có dữ liệu
    assert rec.weighted_score({name: None for name in WEIGHTS}) == 0.0


# ---------------------------------------------------------------------------
# Xếp hạng qua API (Sân A: 100k/150k tại 10.78,106.70 — Sân B: 200k/260k tại 10.85,106.75)
# ---------------------------------------------------------------------------
def test_anonymous_request_without_location_uses_only_available_criteria(client, world):
    by_name, order = recommend(client)
    assert set(order) == {"Sân A", "Sân B"}
    for item in by_name.values():
        assert item["distance_score"] is None and item["preference_score"] is None and item["distance_km"] is None
        assert item["criteria_used"] == ["price", "time", "rating"]
        assert 0 <= item["score"] <= 1 and item["time_score"] == 1.0
    assert by_name["Sân A"]["price_score"] == 1.0 and by_name["Sân B"]["price_score"] == 0.0
    assert order[0] == "Sân A"
    assert by_name["Sân A"]["avg_price"] < by_name["Sân B"]["avg_price"]


def test_distance_radius_and_budget(client, world):
    near_a, order = recommend(client, latitude=10.78, longitude=106.70)
    assert near_a["Sân A"]["distance_km"] == 0 and near_a["Sân A"]["distance_score"] == 1.0
    assert 0 < near_a["Sân B"]["distance_score"] < 1 and near_a["Sân B"]["distance_km"] > 5
    assert order[0] == "Sân A" and "distance" in near_a["Sân A"]["criteria_used"]

    _, within = recommend(client, latitude=10.78, longitude=106.70, radius_km=3)
    assert within == ["Sân A"]

    rich, _ = recommend(client, budget_max=400000)
    assert rich["Sân A"]["price_score"] == rich["Sân B"]["price_score"] == 1.0
    tight, _ = recommend(client, budget_max=100000)
    assert tight["Sân A"]["price_score"] > tight["Sân B"]["price_score"] == 0.0


def test_profile_supplies_location_while_budget_and_amenities_come_from_the_request(client, db, world):
    roof, parking = Amenity(name="Mái che"), Amenity(name="Bãi xe")
    db.add_all([roof, parking])
    world.venue_b.amenities = [roof, parking]
    db.commit()
    player = make_user(db, latitude=10.85, longitude=106.75)

    by_name, _ = recommend(client, player)
    assert by_name["Sân B"]["distance_km"] == 0 and by_name["Sân A"]["distance_km"] > 5     # vị trí lấy từ hồ sơ
    assert all(item["preference_score"] is None and "preference" not in item["criteria_used"] for item in by_name.values())
    assert by_name["Sân A"]["price_score"] == 1.0 and by_name["Sân B"]["price_score"] == 0.0  # không có ngân sách: so giá giữa các sân

    asked, order = recommend(client, player, amenity_ids=[roof.id, parking.id], budget_max=500000)
    assert asked["Sân B"]["preference_score"] == 1.0 and asked["Sân A"]["preference_score"] == 0.0
    assert asked["Sân A"]["price_score"] == asked["Sân B"]["price_score"] == 1.0
    assert order[0] == "Sân B"
    half, _ = recommend(client, player, amenity_ids=[roof.id, 99999])
    assert half["Sân B"]["preference_score"] == 0.5


def test_time_score_reflects_remaining_free_slots(client, world, clock):
    day = clock.day(1)
    before, _ = recommend(client, target_date=day.isoformat())
    assert before["Sân A"]["free_slots"] == before["Sân A"]["total_slots"] == 36   # 2 sân x 18 khung

    confirmed_booking(client, world.p1, world.court, day, hours=tuple(range(5, 14)))
    after, _ = recommend(client, target_date=day.isoformat())
    assert after["Sân A"]["free_slots"] == 27 and after["Sân A"]["time_score"] == 0.75
    assert after["Sân B"]["time_score"] == 1.0

    evening, _ = recommend(client, target_date=day.isoformat(), time_from="18:00:00", time_to="21:00:00")
    assert evening["Sân A"]["total_slots"] == 6 and evening["Sân A"]["avg_price"] == 150000


def test_slots_already_past_today_do_not_count(client, world, clock):
    clock.set(clock.today, 21, 30)
    today, _ = recommend(client)
    assert today["Sân A"]["total_slots"] == 2 and today["Sân A"]["time_score"] == 1.0   # chỉ còn khung 22:00 của 2 sân
    clock.set(clock.today, 22, 30)
    late, _ = recommend(client)
    assert late["Sân A"]["total_slots"] == 0 and late["Sân A"]["time_score"] == 0.0


def test_rating_uses_bayesian_average_not_a_made_up_default(client, db, world):
    none_yet, _ = recommend(client)
    assert none_yet["Sân A"]["avg_rating"] == none_yet["Sân B"]["avg_rating"] == 4.0
    assert none_yet["Sân A"]["review_count"] == 0

    db.add_all([Review(user_id=p.id, venue_id=world.venue_b.id, rating=5.0) for p in world.players])
    db.add(Review(user_id=world.p1.id, venue_id=world.venue_a.id, rating=1.0))
    db.commit()
    rated, _ = recommend(client)
    assert rated["Sân B"]["review_count"] == 3 and rated["Sân A"]["review_count"] == 1
    assert 4.0 < rated["Sân B"]["avg_rating"] < 5.0 and 1.0 < rated["Sân A"]["avg_rating"] < 4.0
    assert rated["Sân B"]["rating_score"] > rated["Sân A"]["rating_score"]


def test_inactive_venues_are_excluded_and_top_n_is_respected(client, db, world):
    make_venue(db, world.owner_a, name="Đang bảo trì", status="MAINTENANCE")
    make_venue(db, world.owner_a, name="Chờ duyệt", status="PENDING")
    _, order = recommend(client)
    assert set(order) == {"Sân A", "Sân B"}
    assert len(recommend(client, top_n=1)[1]) == 1
    assert client.get(URL, params={"top_n": 0}).status_code == 422
    assert client.get(URL, params={"latitude": 123}).status_code == 422


def test_results_are_sorted_by_score(client, db, world):
    for index in range(4):
        make_venue(db, world.owner_a, name=f"Thêm {index}", base=120000 + 30000 * index, lat=10.78 + 0.02 * index)
    response = client.get(URL, params={"latitude": 10.78, "longitude": 106.70, "top_n": 20}).json()
    scores = [item["score"] for item in response]
    assert len(scores) == 6 and scores == sorted(scores, reverse=True)
