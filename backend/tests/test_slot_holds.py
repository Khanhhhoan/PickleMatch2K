"""Giữ chỗ tạm 5 phút: bộ nhớ tiến trình, Redis (client giả) và hành vi khi Redis lỗi."""
import time as real_time

import pytest

from app.core import rate_limit
from app.core.booking_policy import MAX_HELD_SLOTS_PER_USER
from app.core.config import settings
from app.core.redis_client import reset_redis
from app.services import slot_lock_service
from app.services.slot_lock_service import slot_lock_manager
from helpers import auth, create_booking, slot

BOOKINGS = "/api/v1/bookings"


class FakeRedis:
    """Bản tối giản của các lệnh Redis mà ứng dụng dùng, có đồng hồ riêng để thử hết hạn."""

    def __init__(self):
        self.values, self.sets, self.offset = {}, {}, 0.0

    def _now(self):
        return real_time.time() + self.offset

    def _alive(self, key):
        item = self.values.get(key)
        if item and item[1] is not None and item[1] <= self._now():
            del self.values[key]
            return None
        return item

    def set(self, key, value, nx=False, ex=None):
        if nx and self._alive(key):
            return None
        self.values[key] = (value, self._now() + ex if ex else None)
        return True

    def get(self, key):
        item = self._alive(key)
        return item[0] if item else None

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)

    def ttl(self, key):
        item = self._alive(key)
        if not item:
            return -2
        return -1 if item[1] is None else int(item[1] - self._now())

    def incr(self, key):
        item = self._alive(key)
        value = int(item[0]) + 1 if item else 1
        self.values[key] = (str(value), item[1] if item else None)
        return value

    def expire(self, key, seconds):
        if key in self.values:
            self.values[key] = (self.values[key][0], self._now() + seconds)
        return True

    def sadd(self, name, member):
        self.sets.setdefault(name, set()).add(member)

    def srem(self, name, member):
        self.sets.get(name, set()).discard(member)

    def smembers(self, name):
        return set(self.sets.get(name, set()))


class BrokenRedis:
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise ConnectionError("redis is down")
        return fail


@pytest.fixture(params=["memory", "redis"])
def store(request):
    """Chạy cùng một bộ kiểm tra trên cả hai nơi lưu giữ chỗ."""
    fake = FakeRedis() if request.param == "redis" else None
    reset_redis(fake)
    yield fake
    reset_redis(None)


def hold(user_id, court_id=1, start="18:00:00", venue_id=1, day="2030-01-01", **kwargs):
    return slot_lock_manager.hold_slot(venue_id=venue_id, court_id=court_id, court_name="Sân 1", slot_date=day,
                                       start_time=start, end_time="19:00:00", user_id=user_id, **kwargs)


# ---------------------------------------------------------------------------
# Hành vi chung của hai nơi lưu
# ---------------------------------------------------------------------------
def test_a_held_slot_cannot_be_held_by_someone_else(store):
    assert hold(1)[0] is True
    ok, message = hold(2)
    assert ok is False and "tạm giữ" in message
    assert hold(1)[0] is True  # chính người giữ được gia hạn
    assert slot_lock_manager.is_slot_held_by_other(1, "2030-01-01", "18:00", user_id=2) is True
    assert slot_lock_manager.is_slot_held_by_other(1, "2030-01-01", "18:00:00", user_id=1) is False


def test_only_the_holder_can_release(store):
    hold(1)
    assert slot_lock_manager.release_slot(1, 1, "2030-01-01", "18:00:00", user_id=2) is False
    assert slot_lock_manager.release_slot(1, 1, "2030-01-01", "18:00", user_id=1) is True
    assert slot_lock_manager.release_slot(1, 1, "2030-01-01", "18:00", user_id=1) is False
    assert hold(2)[0] is True


def test_holds_are_listed_per_venue_and_day_with_time_remaining(store):
    hold(1, court_id=1, start="18:00:00")
    hold(2, court_id=2, start="19:00")
    hold(3, court_id=9, venue_id=2)
    hold(4, court_id=1, start="20:00", day="2030-01-02")

    listed = slot_lock_manager.get_holds_for_venue(1, "2030-01-01")
    assert sorted((h["court_id"], h["start_time"], h["user_id"]) for h in listed) == [(1, "18:00", 1), (2, "19:00", 2)]
    assert all(0 < h["seconds_remaining"] <= 300 for h in listed)


def test_a_player_cannot_hold_an_unlimited_number_of_slots(store):
    for index in range(MAX_HELD_SLOTS_PER_USER):
        assert hold(1, court_id=index + 1)[0] is True
    ok, message = hold(1, court_id=99)
    assert ok is False and str(MAX_HELD_SLOTS_PER_USER) in message
    assert hold(1, court_id=1)[0] is True   # gia hạn slot đang giữ không tính là giữ thêm
    assert hold(2, court_id=99)[0] is True  # giới hạn tính riêng cho từng người


def test_booking_a_slot_clears_its_hold(store):
    hold(1)
    slot_lock_manager.release_after_booking(1, "2030-01-01", "18:00:00")
    assert slot_lock_manager.get_holds_for_venue(1, "2030-01-01") == []
    assert hold(2)[0] is True


def test_holds_expire(store, monkeypatch):
    hold(1, hold_seconds=60)
    if store is None:
        class _Later:
            @staticmethod
            def time():
                return real_time.time() + 61
        monkeypatch.setattr(slot_lock_service, "time", _Later)
    else:
        store.offset = 61

    assert slot_lock_manager.get_holds_for_venue(1, "2030-01-01") == []
    assert hold(2)[0] is True


# ---------------------------------------------------------------------------
# Redis lỗi
# ---------------------------------------------------------------------------
def test_redis_outage_falls_back_to_process_memory():
    reset_redis(BrokenRedis())
    try:
        assert hold(1)[0] is True
        assert hold(2)[0] is False
        assert len(slot_lock_manager.get_holds_for_venue(1, "2030-01-01")) == 1
    finally:
        reset_redis(None)


def test_login_rate_limit_counts_in_redis_when_available():
    fake = FakeRedis()
    reset_redis(fake)
    try:
        limiter = rate_limit.LoginRateLimiter()
        for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
            limiter.register_failure("ip:user")
        assert limiter.retry_after("ip:user") == 0
        limiter.register_failure("ip:user")
        assert 0 < limiter.retry_after("ip:user") <= settings.LOGIN_WINDOW_SECONDS
        fake.offset = settings.LOGIN_WINDOW_SECONDS + 1
        assert limiter.retry_after("ip:user") == 0
        limiter.register_failure("ip:user")
        limiter.reset("ip:user")
        assert fake.get("login_fail:ip:user") is None
    finally:
        reset_redis(None)


# ---------------------------------------------------------------------------
# Qua API
# ---------------------------------------------------------------------------
def hold_api(client, user, court, day, hour=18):
    payload = {"venue_id": court.venue_id, **slot(court, day, hour)}
    return client.post(f"{BOOKINGS}/hold-slot", json=payload, headers=auth(user))


def availability(client, venue, day, user=None):
    response = client.get(f"/api/v1/search/venues/{venue.id}/availability", params={"target_date": day.isoformat()},
                          headers=auth(user) if user else {})
    assert response.status_code == 200, response.text
    return {(c["court_id"], s["start_time"]): s for c in response.json()["courts"] for s in c["slots"]}


def test_hold_endpoint_and_availability_flags(client, world, clock):
    day, court = clock.day(1), world.court
    assert hold_api(client, world.p1, court, day).status_code == 200
    assert hold_api(client, world.p2, court, day).status_code == 409

    key = (court.id, "18:00:00")
    mine, theirs, public = (availability(client, world.venue_a, day, user)[key] for user in (world.p1, world.p2, None))
    assert (mine["held_by_me"], mine["is_held"]) == (True, False)
    assert (theirs["held_by_me"], theirs["is_held"]) == (False, True)
    assert (public["held_by_me"], public["is_held"]) == (False, True)
    assert all(s["is_available"] and s["held_by_user"] is None for s in (mine, theirs, public))  # không lộ tên người giữ
    assert 0 < theirs["hold_seconds_remaining"] <= 300


def test_hold_endpoint_validation(client, world, clock):
    day = clock.day(1)
    wrong_venue = {"venue_id": world.venue_b.id, **slot(world.court, day, 18)}
    assert client.post(f"{BOOKINGS}/hold-slot", json=wrong_venue, headers=auth(world.p1)).status_code == 404
    off_grid = {"venue_id": world.venue_a.id, **slot(world.court, day, 18, 30)}
    assert client.post(f"{BOOKINGS}/hold-slot", json=off_grid, headers=auth(world.p1)).status_code == 400
    assert client.post(f"{BOOKINGS}/hold-slot", json={"venue_id": world.venue_a.id, **slot(world.court, day, 18)}).status_code == 401


def test_a_hold_blocks_other_players_from_booking_but_not_the_holder(client, world, clock):
    day, court = clock.day(1), world.court
    hold_api(client, world.p1, court, day)

    create_booking(client, world.p2, court, day, hours=(18,), expect=409)
    create_booking(client, world.p1, court, day, hours=(18,))
    assert slot_lock_manager.get_holds_for_venue(world.venue_a.id, day.isoformat()) == []


def test_release_endpoint(client, world, clock):
    day, court = clock.day(1), world.court
    hold_api(client, world.p1, court, day)
    body = {"venue_id": court.venue_id, "court_id": court.id, "date": day.isoformat(), "start_time": "18:00:00"}

    assert client.post(f"{BOOKINGS}/release-slot", json=body, headers=auth(world.p2)).json()["released"] is False
    assert client.post(f"{BOOKINGS}/release-slot", json=body, headers=auth(world.p1)).json()["released"] is True
    assert hold_api(client, world.p2, court, day).status_code == 200
