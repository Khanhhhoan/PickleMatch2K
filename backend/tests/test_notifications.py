"""Thông báo trong ứng dụng: phòng đấu bị hủy, xin vào phòng / được duyệt; lưu lại, không trùng, chỉ chủ nhân xem được."""
from app.models.match import Match
from app.models.notification import Notification
from app.services import match_service, notification_service
from helpers import auth, confirmed_booking

MATCHES = "/api/v1/matches"
BOOKINGS = "/api/v1/bookings"
NOTIFICATIONS = "/api/v1/notifications"


def open_room(client, host, booking, **extra):
    response = client.post(MATCHES, json={"booking_id": booking["id"], **extra}, headers=auth(host))
    assert response.status_code == 200, response.text
    return response.json()


def enter(client, host, user, room):
    assert client.post(f"{MATCHES}/{room['id']}/join", headers=auth(user)).status_code == 200
    assert client.post(f"{MATCHES}/{room['id']}/requests/{user.id}/accept", headers=auth(host)).status_code == 200


def inbox(client, user):
    response = client.get(NOTIFICATIONS, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def kinds(client, user):
    return [n["kind"] for n in inbox(client, user)["items"]]


def test_members_and_waiting_players_learn_that_the_host_cancelled_the_room(client, db, world, clock):
    room = open_room(client, world.p1, confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,)))
    enter(client, world.p1, world.p2, room)
    client.post(f"{MATCHES}/{room['id']}/join", headers=auth(world.p3))           # đang chờ duyệt

    client.post(f"{MATCHES}/{room['id']}/leave", headers=auth(world.p1))           # chủ phòng hủy phòng
    for player in (world.p2, world.p3):
        latest = inbox(client, player)["items"][0]
        assert latest["kind"] == "MATCH_CANCELLED" and "chủ phòng đã hủy phòng" in latest["body"]
        assert "Sân A" in latest["body"] and latest["link"] == "/matches?tab=my_matches"
    assert "MATCH_CANCELLED" not in kinds(client, world.p1)                       # người tự hủy không cần được báo


def test_a_room_cancelled_with_its_booking_is_announced_with_the_reason(client, db, world, clock):
    by_player = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    by_venue = confirmed_booking(client, world.p2, world.venue_a.courts[1], clock.day(1), hours=(18,))
    first, second = open_room(client, world.p1, by_player), open_room(client, world.p2, by_venue)
    enter(client, world.p1, world.p3, first)
    assert second["id"] != first["id"]

    client.post(f"{BOOKINGS}/{by_player['id']}/cancel", headers=auth(world.p1),
                json={"bank_account": "1", "bank_name": "MB", "account_holder": "A"})
    assert "chủ phòng đã hủy lịch đặt sân" in inbox(client, world.p3)["items"][0]["body"]

    client.put(f"{BOOKINGS}/{by_venue['id']}/status", json={"status": "CANCELLED"}, headers=auth(world.owner_a))
    host_inbox = inbox(client, world.p2)["items"]
    assert host_inbox[0]["kind"] == "MATCH_CANCELLED" and "cụm sân đã hủy" in host_inbox[0]["body"]


def test_background_cancellation_is_announced_once_even_if_it_runs_again(client, db, world, clock):
    day = clock.day(1)
    room = open_room(client, world.p1, confirmed_booking(client, world.p1, world.court, day, hours=(9,)), num_players=4)
    enter(client, world.p1, world.p2, room)

    clock.set(day, 10, 5)
    match_service.auto_update_expired_matches(db)
    match = db.get(Match, room["id"])
    notification_service.notify_match_cancelled(db, match, "chạy lại")          # tác vụ chạy lại: không gửi trùng
    db.commit()
    for player in (world.p1, world.p2):
        cancelled = [n for n in inbox(client, player)["items"] if n["kind"] == "MATCH_CANCELLED"]
        assert len(cancelled) == 1 and "chưa đủ người" in cancelled[0]["body"]
    assert db.query(Notification).filter_by(kind="MATCH_CANCELLED").count() == 2


def test_host_hears_about_requests_and_players_about_decisions(client, world, clock):
    room = open_room(client, world.p1, confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,)))
    client.post(f"{MATCHES}/{room['id']}/join", headers=auth(world.p2))
    client.post(f"{MATCHES}/{room['id']}/join", headers=auth(world.p3))
    assert kinds(client, world.p1) == ["MATCH_REQUEST", "MATCH_REQUEST"]

    client.post(f"{MATCHES}/{room['id']}/requests/{world.p2.id}/accept", headers=auth(world.p1))
    client.post(f"{MATCHES}/{room['id']}/requests/{world.p3.id}/reject", headers=auth(world.p1))
    assert kinds(client, world.p2) == ["MATCH_ACCEPTED"] and kinds(client, world.p3) == ["MATCH_REJECTED"]


def test_admin_cancelling_a_room_notifies_its_people(client, world, clock):
    room = open_room(client, world.p1, confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,)))
    enter(client, world.p1, world.p2, room)
    client.put(f"{MATCHES}/admin/{room['id']}/status", json={"status": "CANCELLED"}, headers=auth(world.admin))
    assert "quản trị viên" in inbox(client, world.p2)["items"][0]["body"]
    assert inbox(client, world.p1)["items"][0]["kind"] == "MATCH_CANCELLED"


def test_reading_notifications_and_keeping_them_private(client, world, clock):
    room = open_room(client, world.p1, confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,)))
    client.post(f"{MATCHES}/{room['id']}/join", headers=auth(world.p2))
    client.post(f"{MATCHES}/{room['id']}/join", headers=auth(world.p3))

    mine = inbox(client, world.p1)
    assert mine["unread_count"] == 2 and all(n["read_at"] is None for n in mine["items"])
    first = mine["items"][0]["id"]
    assert client.post(f"{NOTIFICATIONS}/{first}/read", headers=auth(world.p2)).status_code == 404   # không phải của p2
    read = client.post(f"{NOTIFICATIONS}/{first}/read", headers=auth(world.p1)).json()
    assert read["read_at"] is not None and inbox(client, world.p1)["unread_count"] == 1
    assert client.post(f"{NOTIFICATIONS}/read-all", headers=auth(world.p1)).json() == {"updated": 1}
    assert inbox(client, world.p1)["unread_count"] == 0
    assert inbox(client, world.p2)["items"] == []                                   # người khác không thấy
    assert client.get(NOTIFICATIONS).status_code == 401
