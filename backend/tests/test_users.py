"""Hồ sơ cá nhân, đổi mật khẩu và quản trị tài khoản."""
import pytest

from app.models.user import PlayerProfile, User
from app.models.venue import Amenity, Venue
from helpers import auth, confirmed_booking, make_user

USERS = "/api/v1/users"
PROFILE = f"{USERS}/me/profile"


def update_profile(client, user, **fields):
    return client.put(PROFILE, json=fields, headers=auth(user))


# ---------------------------------------------------------------------------
# Hồ sơ
# ---------------------------------------------------------------------------
def test_player_updates_matching_profile(client, db):
    led, roof = Amenity(name="Đèn LED"), Amenity(name="Mái che")
    db.add_all([led, roof])
    db.commit()
    player = make_user(db)

    response = update_profile(
        client, player, full_name="  Nguyễn An ", phone="0901 234 567", skill_level=3.5, play_style="Offensive",
        latitude=10.78, longitude=106.7, purpose="practice", budget_max=200000,
        availability=["sat_morning", "mon_evening", "mon_evening"], preferred_amenity_ids=[roof.id, 9999, led.id],
        company_name="Không áp dụng cho người chơi",
    )
    assert response.status_code == 200, response.text
    profile = response.json()["player_profile"]
    assert (profile["full_name"], profile["phone"], profile["skill_level"]) == ("Nguyễn An", "0901234567", 3.5)
    assert (profile["purpose"], profile["budget_max"]) == ("practice", 200000)
    assert profile["availability"] == ["mon_evening", "sat_morning"]           # bỏ trùng, xếp theo thứ tự trong tuần
    assert profile["preferred_amenity_ids"] == [led.id, roof.id]              # bỏ id tiện ích không tồn tại
    assert response.json()["owner_profile"] is None

    # Chỉ trường được gửi mới thay đổi; ngân sách 0 nghĩa là không giới hạn
    cleared = update_profile(client, player, budget_max=0, availability=[]).json()["player_profile"]
    assert (cleared["budget_max"], cleared["availability"], cleared["purpose"], cleared["skill_level"]) == (None, [], "practice", 3.5)


@pytest.mark.parametrize("fields", [
    {"purpose": "gambling"},
    {"availability": ["mon_midnight"]},
    {"skill_level": 0.5}, {"skill_level": 9},
    {"latitude": 91}, {"longitude": -181},
    {"budget_max": -1},
    {"phone": "abc"},
    {"date_of_birth": "2999-01-01"},
    {"matches_played": 3, "matches_won": 5},
])
def test_profile_validation(client, db, fields):
    assert update_profile(client, make_user(db), **fields).status_code == 422


def test_wins_cannot_exceed_stored_matches_played(client, db):
    player = make_user(db, matches_played=5, matches_won=2)
    assert update_profile(client, player, matches_won=9).status_code == 400
    body = update_profile(client, player, matches_won=4).json()["player_profile"]
    assert (body["matches_won"], body["win_rate"]) == (4, 80.0)
    assert make_user(db).player_profile.win_rate is None  # chưa có trận nào thì không bịa tỷ lệ thắng


def test_profile_fields_depend_on_role(client, world):
    owner = update_profile(client, world.owner_a, full_name="Chủ A", bank_account="999888777 - ACB",
                           company_name="CTY A", skill_level=4.0).json()
    assert (owner["owner_profile"]["bank_account"], owner["owner_profile"]["company_name"]) == ("999888777 - ACB", "CTY A")
    assert owner["player_profile"] is None

    staff = update_profile(client, world.staff_a, full_name="NV A", phone="0909090909").json()["staff_profile"]
    assert (staff["full_name"], staff["phone"], staff["venue_id"], staff["venue_name"]) == (
        "NV A", "0909090909", world.venue_a.id, "Sân A")
    assert update_profile(client, world.admin, full_name="Admin").status_code == 400


def test_profile_options_are_shared_with_the_matching_model(client):
    options = client.get(f"{USERS}/profile-options").json()
    assert options["purposes"] == ["recreational", "practice", "competitive"]
    assert options["days"][0] == "mon" and options["periods"] == ["morning", "afternoon", "evening"]
    assert "All-Round" in options["play_styles"]


def test_change_password(client, db):
    user = make_user(db, email="pw@example.com", password="old-secret")
    path, headers = f"{USERS}/me/change-password", auth(user)

    assert client.post(path, json={"current_password": "wrong", "new_password": "new-secret"}, headers=headers).status_code == 400
    assert client.post(path, json={"current_password": "old-secret", "new_password": "old-secret"}, headers=headers).status_code == 400
    assert client.post(path, json={"current_password": "old-secret", "new_password": "123"}, headers=headers).status_code == 422
    assert client.post(path, json={"current_password": "old-secret", "new_password": "new-secret"}, headers=headers).status_code == 200

    def login(password):
        return client.post("/api/v1/auth/login", data={"username": "pw@example.com", "password": password}).status_code

    assert (login("old-secret"), login("new-secret")) == (401, 200)


# ---------------------------------------------------------------------------
# Admin quản lý tài khoản
# ---------------------------------------------------------------------------
def admin_create(client, world, **fields):
    payload = {"email": "created@example.com", "password": "secret123", **fields}
    return client.post(f"{USERS}/admin/users", json=payload, headers=auth(world.admin))


def test_admin_creates_accounts_of_each_role(client, db, world):
    player = admin_create(client, world, role="PLAYER", full_name="VĐV", skill_level=4.0, play_style="Defensive").json()
    assert player["player_profile"]["skill_level"] == 4.0 and player["player_profile"]["latitude"] is None

    assert admin_create(client, world, email="s1@example.com", role="STAFF").status_code == 400
    assert admin_create(client, world, email="s1@example.com", role="STAFF", venue_id=9999).status_code == 404
    staff = admin_create(client, world, email="s1@example.com", role="STAFF", venue_id=world.venue_b.id).json()
    assert staff["staff_profile"]["venue_id"] == world.venue_b.id

    assert admin_create(client, world, email="a2@example.com", role="ADMIN").json()["role"] == "ADMIN"
    assert admin_create(client, world, email="s1@example.com", role="PLAYER").status_code == 400     # trùng email
    assert admin_create(client, world, email="x@example.com", role="SUPERUSER").status_code == 422


def test_new_owner_gets_a_starter_venue_that_stays_hidden_until_it_has_an_address(client, db, world):
    hidden = admin_create(client, world, email="o1@example.com", role="OWNER", full_name="Chủ Mới").json()
    listed = admin_create(client, world, email="o2@example.com", role="OWNER", venue_name="Sân Có Địa Chỉ",
                          venue_address="12 Lê Lợi, Quận 1", bank_account="123456789 - VIB").json()

    first = db.query(Venue).filter_by(owner_id=hidden["id"]).one()
    second = db.query(Venue).filter_by(owner_id=listed["id"]).one()
    assert (first.status, first.name) == ("INACTIVE", "Cụm Sân Chủ Mới")
    assert (second.status, second.address, len(second.courts), len(second.operating_hours)) == ("ACTIVE", "12 Lê Lợi, Quận 1", 4, 7)
    assert listed["owner_profile"]["bank_account"] == "123456789 - VIB"

    public = [v["name"] for v in client.get("/api/v1/venues").json()]
    assert "Sân Có Địa Chỉ" in public and "Cụm Sân Chủ Mới" not in public


def test_admin_updates_and_locks_accounts(client, db, world):
    target = f"{USERS}/admin/users/{world.p1.id}"
    admin = auth(world.admin)

    updated = client.put(target, json={"email": "Renamed@Example.com", "full_name": "Tên Mới", "skill_level": 4.5,
                                       "password": "brand-new-pw"}, headers=admin).json()
    assert (updated["email"], updated["player_profile"]["full_name"], updated["player_profile"]["skill_level"]) == (
        "renamed@example.com", "Tên Mới", 4.5)
    assert client.post("/api/v1/auth/login", data={"username": "renamed@example.com", "password": "brand-new-pw"}).status_code == 200
    assert client.put(target, json={"email": world.p2.email}, headers=admin).status_code == 400
    assert client.put(f"{USERS}/admin/users/99999", json={"full_name": "x"}, headers=admin).status_code == 404

    locked = client.put(f"{target}/active", json={"is_active": False}, headers=admin).json()
    assert locked["is_active"] is False
    assert client.get(f"{USERS}/me", headers=auth(world.p1)).status_code == 401
    assert client.put(f"{target}/active", json={"is_active": True}, headers=admin).json()["is_active"] is True
    assert client.get(f"{USERS}/me", headers=auth(world.p1)).status_code == 200


def test_admin_cannot_lock_demote_or_delete_themselves(client, world):
    own, admin = f"{USERS}/admin/users/{world.admin.id}", auth(world.admin)
    assert client.put(own, json={"role": "PLAYER"}, headers=admin).status_code == 400
    assert client.put(own, json={"is_active": False}, headers=admin).status_code == 400
    assert client.put(f"{own}/active", json={"is_active": False}, headers=admin).status_code == 400
    assert client.delete(own, headers=admin).status_code == 400
    assert client.get(f"{USERS}/me", headers=admin).json()["role"] == "ADMIN"


def test_delete_removes_unused_accounts_but_only_locks_accounts_with_history(client, db, world, clock):
    confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    admin = auth(world.admin)
    booked_id, unused_id, owner_id = world.p1.id, world.p3.id, world.owner_a.id

    with_history = client.delete(f"{USERS}/admin/users/{booked_id}", headers=admin).json()
    unused = client.delete(f"{USERS}/admin/users/{unused_id}", headers=admin).json()
    owner = client.delete(f"{USERS}/admin/users/{owner_id}", headers=admin).json()
    assert (with_history["status"], unused["status"], owner["status"]) == ("deactivated", "success", "deactivated")

    db.expunge_all()
    assert db.get(User, unused_id) is None
    assert db.query(PlayerProfile).filter_by(user_id=unused_id).count() == 0     # hồ sơ được xóa kèm tài khoản
    assert db.get(User, booked_id).is_active is False and db.get(User, owner_id).is_active is False
    assert len(client.get(f"{USERS}/admin/users", headers=admin).json()) == 7


def test_owner_deleting_staff_keeps_audit_trail(client, db, world, clock):
    payload = {"court_id": world.court.id, "date": clock.day(1).isoformat(), "start_time": "09:00:00",
               "end_time": "10:00:00", "payment_method": "CASH"}
    assert client.post("/api/v1/bookings/desk", json=payload, headers=auth(world.staff_a)).status_code == 200
    idle_id, busy_id = make_user(db, "STAFF", venue=world.venue_a).id, world.staff_a.id
    owner = auth(world.owner_a)

    assert client.delete(f"{USERS}/owner/staff/{busy_id}", headers=owner).json()["status"] == "deactivated"
    assert client.delete(f"{USERS}/owner/staff/{idle_id}", headers=owner).json()["status"] == "success"
    db.expunge_all()
    assert db.get(User, busy_id).is_active is False and db.get(User, idle_id) is None


def test_staff_who_only_handled_bookings_is_locked_not_deleted(client, db, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(9,))
    clock.set(day, 8, 55)
    assert client.post(f"/api/v1/bookings/{booking['id']}/checkin", headers=auth(world.staff_a)).status_code == 200

    outcome = client.delete(f"{USERS}/admin/users/{world.staff_a.id}", headers=auth(world.admin)).json()
    assert outcome["status"] == "deactivated"
    db.expire_all()
    assert db.get(User, world.staff_a.id).is_active is False
