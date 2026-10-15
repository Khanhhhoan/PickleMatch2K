"""
Ma trận phân quyền:
- mọi endpoint không thuộc danh sách công khai đều đòi đăng nhập;
- kiểm tra theo vai trò (người chơi / nhân viên / chủ sân / admin);
- kiểm tra theo quyền sở hữu: chủ sân A và nhân viên của A không chạm được vào dữ liệu của cụm sân B.
"""
import re

import pytest

from app.main import app
from helpers import auth, confirmed_booking, create_booking, make_user

API = "/api/v1"

PUBLIC_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/venues"),
    ("GET", "/api/v1/venues/amenities"),
    ("GET", "/api/v1/venues/{venue_id}"),
    ("GET", "/api/v1/venues/{venue_id}/reviews"),
    ("GET", "/api/v1/search/venues"),
    ("GET", "/api/v1/search/venues/{venue_id}/availability"),
    ("GET", "/api/v1/recommendations/venues"),
    ("GET", "/api/v1/matches"),
    ("GET", "/api/v1/payments/config"),
    ("GET", "/api/v1/users/profile-options"),
    ("POST", "/api/v1/payments/sepay-webhook"),  # xác thực bằng khóa API của SePay, không dùng token người dùng
}

ADMIN_ONLY = [
    ("GET", "/users"), ("GET", "/users/admin/users"), ("POST", "/users/admin/users"),
    ("PUT", "/users/admin/users/1"), ("PUT", "/users/admin/users/1/active"), ("DELETE", "/users/admin/users/1"),
    ("GET", "/venues/admin/all"), ("POST", "/venues/admin"), ("PUT", "/venues/admin/1"),
    ("DELETE", "/venues/admin/1"), ("PUT", "/venues/admin/1/assign-owner"),
    ("GET", "/bookings"), ("GET", "/bookings/admin/all"), ("DELETE", "/bookings/admin/1"),
    ("GET", "/matches/admin/all"), ("POST", "/matches/admin/create"), ("PUT", "/matches/admin/1/status"),
    ("PUT", "/matches/admin/1"), ("POST", "/matches/admin/1/participants"),
    ("DELETE", "/matches/admin/1/participants/1"), ("DELETE", "/matches/admin/1"),
]

OWNER_OR_ADMIN = [
    ("POST", "/venues"), ("PUT", "/venues/1"), ("PUT", "/venues/1/status"), ("POST", "/venues/1/upload-image"),
    ("DELETE", "/venues/1/images?image_url=x"), ("POST", "/venues/1/courts"), ("PUT", "/venues/1/courts/1"),
    ("DELETE", "/venues/1/courts/1"), ("POST", "/venues/1/operating-hours"), ("PUT", "/venues/1/operating-hours"),
    ("POST", "/venues/1/price-rules"), ("POST", "/venues/1/pricing"), ("PUT", "/venues/1/pricing"),
    ("GET", "/users/owner/staff"), ("POST", "/users/owner/staff"), ("PUT", "/users/owner/staff/1"),
    ("DELETE", "/users/owner/staff/1"),
]

VENUE_STAFF = [
    ("POST", "/bookings/desk"), ("POST", "/bookings/staff/walkin"), ("POST", "/bookings/1/checkin"),
    ("POST", "/bookings/1/collect"), ("POST", "/bookings/1/confirm-refund"), ("PUT", "/bookings/1/status"),
    ("PUT", "/bookings/staff/1/reschedule"), ("GET", "/bookings/owner/list"), ("GET", "/bookings/owner/stats"),
    ("GET", "/bookings/staff/stats"), ("GET", "/venues/me"),
    ("GET", "/payments/shift-closings"), ("POST", "/payments/shift-closings"),
]


def api_routes():
    """Mọi (phương thức, đường dẫn) mà ứng dụng công bố, lấy từ lược đồ OpenAPI."""
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                yield method.upper(), path


def test_every_non_public_endpoint_requires_a_login(client):
    routes = list(api_routes())
    assert len(routes) > 80  # bảo đảm phép kiểm tra thật sự quét toàn bộ API
    unprotected = []
    for method, path in routes:
        if (method, path) in PUBLIC_ROUTES:
            continue
        response = client.request(method, re.sub(r"\{[^}]+\}", "1", path))
        if response.status_code != 401:
            unprotected.append((method, path, response.status_code))
    assert unprotected == []


def test_public_route_list_matches_the_application():
    existing = set(api_routes())
    assert PUBLIC_ROUTES <= existing, PUBLIC_ROUTES - existing


@pytest.mark.parametrize("method, path", ADMIN_ONLY)
def test_admin_only_endpoints_reject_every_other_role(client, world, method, path):
    for user in (world.p1, world.staff_a, world.owner_a):
        assert client.request(method, API + path, headers=auth(user)).status_code == 403, user.role


@pytest.mark.parametrize("method, path", OWNER_OR_ADMIN)
def test_venue_configuration_is_closed_to_players_and_staff(client, world, method, path):
    for user in (world.p1, world.staff_a):
        assert client.request(method, API + path, headers=auth(user)).status_code == 403, user.role


@pytest.mark.parametrize("method, path", VENUE_STAFF)
def test_counter_operations_are_closed_to_players(client, world, method, path):
    assert client.request(method, API + path, headers=auth(world.p1)).status_code == 403


# ---------------------------------------------------------------------------
# Quyền sở hữu cụm sân
# ---------------------------------------------------------------------------
def test_an_owner_can_configure_only_their_own_venue(client, world):
    a, b = world.venue_a, world.venue_b
    attempts = [
        ("PUT", "/venues/{v}", {"name": "Đổi tên"}),
        ("PUT", "/venues/{v}/status", {"status": "MAINTENANCE"}),
        ("POST", "/venues/{v}/courts", {"name": "Sân mới"}),
        ("PUT", "/venues/{v}/courts/{c}", {"name": "Sân đổi tên"}),
        ("POST", "/venues/{v}/operating-hours", {"day_of_week": 0, "open_time": "06:00", "close_time": "22:00"}),
        ("PUT", "/venues/{v}/operating-hours", {"hours": [{"day_of_week": 0, "open_time": "06:00", "close_time": "22:00"}]}),
        ("POST", "/venues/{v}/price-rules", {"rule_type": "BASE", "price": 90000}),
        ("PUT", "/venues/{v}/pricing", {"base_price": 90000}),
    ]
    for method, template, body in attempts:
        foreign = template.format(v=b.id, c=b.courts[0].id)
        own = template.format(v=a.id, c=a.courts[0].id)
        assert client.request(method, API + foreign, json=body, headers=auth(world.owner_a)).status_code == 403, foreign
        assert client.request(method, API + own, json=body, headers=auth(world.owner_a)).status_code == 200, own
        assert client.request(method, API + foreign, json=body, headers=auth(world.admin)).status_code == 200, foreign

    assert client.delete(f"{API}/venues/{b.id}/courts/{b.courts[1].id}", headers=auth(world.owner_a)).status_code == 403
    assert client.delete(f"{API}/venues/{b.id}/images", params={"image_url": "x"}, headers=auth(world.owner_a)).status_code == 403
    # Sân của cụm B không thao tác được qua đường dẫn của cụm A
    assert client.put(f"{API}/venues/{a.id}/courts/{b.courts[0].id}", json={"name": "x"}, headers=auth(world.owner_a)).status_code == 404


def test_my_venues_is_scoped_and_hides_payout_details_from_staff(client, world):
    def mine(user):
        return client.get(f"{API}/venues/me", headers=auth(user)).json()

    assert [v["name"] for v in mine(world.owner_a)] == ["Sân A"]
    assert [v["name"] for v in mine(world.staff_b)] == ["Sân B"]
    assert len(mine(world.admin)) == 2
    assert mine(world.owner_a)[0]["owner_bank_account"] == "111222333 - MBBank"
    assert mine(world.staff_a)[0]["owner_bank_account"] is None
    # Danh sách công khai không bao giờ chứa tài khoản ngân hàng của chủ sân
    assert "owner_bank_account" not in client.get(f"{API}/venues").json()[0]
    assert "111222333" not in client.get(f"{API}/venues/{world.venue_a.id}").text


def test_staff_can_only_work_on_bookings_of_their_venue(client, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.venue_b.courts[0], day, hours=(18,))
    clock.set(day, 17, 55)
    base = f"{API}/bookings/{booking['id']}"
    actions = [
        ("POST", f"{base}/collect", {"amount": 1000}),
        ("PUT", f"{API}/bookings/staff/{booking['id']}/reschedule", {"start_time": "20:00:00"}),
        ("POST", f"{base}/checkin", None),
        ("PUT", f"{base}/status", {"status": "CANCELLED"}),
        ("POST", f"{base}/confirm-refund", {"bank_reference": "FT26288PERM01"}),
    ]
    for method, path, body in actions:
        for outsider in (world.staff_a, world.owner_a):
            assert client.request(method, path, json=body, headers=auth(outsider)).status_code == 403, (path, outsider.role)
    for method, path, body in actions:
        assert client.request(method, path, json=body, headers=auth(world.staff_b)).status_code == 200, path


def test_booking_lists_are_scoped_to_the_managed_venue(client, world, clock):
    day = clock.day(1)
    create_booking(client, world.p1, world.venue_a.courts[0], day, hours=(9,))
    create_booking(client, world.p2, world.venue_b.courts[0], day, hours=(9,))

    def codes(user, path="/bookings/owner/list"):
        return sorted(b["booking_code"] for b in client.get(API + path, headers=auth(user)).json())

    assert codes(world.owner_a) == codes(world.staff_a) == ["PK2K000001"]
    assert codes(world.owner_b) == codes(world.staff_b) == ["PK2K000002"]
    assert codes(world.admin) == codes(world.admin, "/bookings/admin/all") == ["PK2K000001", "PK2K000002"]
    assert codes(world.p1, "/bookings/me") == ["PK2K000001"] and codes(world.p3, "/bookings/me") == []


def test_staff_without_a_venue_sees_nothing(client, db, world, clock):
    create_booking(client, world.p1, world.court, clock.day(1), hours=(9,))
    floating = make_user(db, "STAFF")
    assert client.get(f"{API}/bookings/owner/list", headers=auth(floating)).json() == []
    assert client.get(f"{API}/venues/me", headers=auth(floating)).json() == []
    assert client.get(f"{API}/payments/transactions", headers=auth(floating)).json() == []
    assert client.get(f"{API}/bookings/staff/stats", headers=auth(floating)).status_code == 400


def test_owner_manages_only_their_own_staff(client, world):
    staff_path = f"{API}/users/owner/staff"
    assert [u["email"] for u in client.get(staff_path, headers=auth(world.owner_a)).json()] == ["staff_a@example.com"]
    assert len(client.get(staff_path, headers=auth(world.admin)).json()) == 2

    new = {"email": "new_staff@example.com", "password": "secret123", "full_name": "NV mới"}
    assert client.post(staff_path, json={**new, "venue_id": world.venue_b.id}, headers=auth(world.owner_a)).status_code == 403
    assert client.post(staff_path, json=new, headers=auth(world.owner_a)).status_code == 422   # bắt buộc chọn cụm sân
    created = client.post(staff_path, json={**new, "venue_id": world.venue_a.id}, headers=auth(world.owner_a))
    assert created.status_code == 200 and created.json()["staff_profile"]["venue_id"] == world.venue_a.id

    foreign = f"{staff_path}/{world.staff_b.id}"
    assert client.put(foreign, json={"full_name": "Chiếm quyền"}, headers=auth(world.owner_a)).status_code == 403
    assert client.delete(foreign, headers=auth(world.owner_a)).status_code == 403
    own = f"{staff_path}/{world.staff_a.id}"
    assert client.put(own, json={"venue_id": world.venue_b.id}, headers=auth(world.owner_a)).status_code == 403
    assert client.put(own, json={"full_name": "Tên mới"}, headers=auth(world.owner_a)).json()["staff_profile"]["full_name"] == "Tên mới"
    assert client.put(f"{staff_path}/{world.p1.id}", json={"full_name": "x"}, headers=auth(world.owner_a)).status_code == 404


def test_hidden_venues_are_visible_only_to_their_managers(client, db, world):
    world.venue_a.status = "INACTIVE"
    db.commit()
    path = f"{API}/venues/{world.venue_a.id}"
    assert client.get(path).status_code == 404
    assert client.get(path, headers=auth(world.p1)).status_code == 404
    assert client.get(path, headers=auth(world.owner_b)).status_code == 404
    for manager in (world.owner_a, world.staff_a, world.admin):
        assert client.get(path, headers=auth(manager)).status_code == 200
    assert [v["name"] for v in client.get(f"{API}/venues").json()] == ["Sân B"]
    assert [v["name"] for v in client.get(f"{API}/search/venues").json()] == ["Sân B"]
