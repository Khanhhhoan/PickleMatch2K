"""Phòng đấu: gắn với đơn đặt sân, tham gia/rời, tự cập nhật theo đơn và theo thời gian, quyền riêng tư, đề xuất."""
import json
from datetime import date, time, timedelta

from app.models.match import Match
from app.services import booking_service, match_service
from helpers import auth, confirmed_booking, create_booking, make_user

MATCHES = "/api/v1/matches"
BOOKINGS = "/api/v1/bookings"


def open_match(client, user, booking, expect=200, **extra):
    response = client.post(MATCHES, json={"booking_id": booking["id"], **extra}, headers=auth(user))
    assert response.status_code == expect, response.text
    return response.json()


def join(client, user, match):
    return client.post(f"{MATCHES}/{match['id']}/join", headers=auth(user))


def leave(client, user, match):
    return client.post(f"{MATCHES}/{match['id']}/leave", headers=auth(user))


def status_of(db, match):
    db.expire_all()
    return db.get(Match, match["id"]).status


# ---------------------------------------------------------------------------
# Mở phòng
# ---------------------------------------------------------------------------
def test_match_takes_court_and_time_from_the_paid_booking(client, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18, 19))
    match = open_match(client, world.p1, booking, required_skill=3.5, num_players=4, purpose="competitive", notes="  Đánh đôi ")

    assert (match["status"], match["booking_id"], match["booking_code"]) == ("OPEN", booking["id"], "PK2K000001")
    assert (match["venue_id"], match["court_id"], match["venue_name"]) == (world.venue_a.id, world.court.id, "Sân A")
    assert (match["date"], match["start_time"], match["end_time"]) == (day.isoformat(), "18:00:00", "20:00:00")
    assert (match["purpose"], match["notes"], match["num_players"]) == ("competitive", "Đánh đôi", 4)
    assert [p["user_id"] for p in match["participants"]] == [world.p1.id]  # chủ phòng tự động là thành viên


def test_match_requires_an_own_paid_and_upcoming_booking(client, world, clock):
    day = clock.day(1)
    unpaid = create_booking(client, world.p1, world.court, day, hours=(9,))
    paid = confirmed_booking(client, world.p1, world.court, day, hours=(18,))

    open_match(client, world.p1, unpaid, expect=400)
    open_match(client, world.p2, paid, expect=404)                 # đơn của người khác
    open_match(client, world.p1, {"id": 9999}, expect=404)
    assert client.post(MATCHES, json={"booking_id": paid["id"]}).status_code == 401
    assert client.post(MATCHES, json={"num_players": 4}, headers=auth(world.p1)).status_code == 422  # bắt buộc có đơn
    for bad in ({"num_players": 1}, {"num_players": 9}, {"required_skill": 9}, {"purpose": "gambling"}):
        open_match(client, world.p1, paid, expect=422, **bad)

    open_match(client, world.p1, paid)
    open_match(client, world.p1, paid, expect=400)                 # mỗi đơn chỉ một phòng đang hoạt động

    clock.set(day, 19, 30)
    open_match(client, world.p1, paid, expect=400)                 # đã qua giờ chơi


def test_a_cancelled_match_can_be_reopened_on_the_same_booking(client, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    first = open_match(client, world.p1, booking)
    assert leave(client, world.p1, first).json()["status"] == "CANCELLED"   # chủ phòng rời đi thì hủy phòng
    assert open_match(client, world.p1, booking)["id"] != first["id"]


# ---------------------------------------------------------------------------
# Tham gia / rời phòng
# ---------------------------------------------------------------------------
def test_join_until_full_then_leave_reopens(client, db, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    match = open_match(client, world.p1, booking, num_players=3)

    assert join(client, world.p1, match).status_code == 400                 # đã ở trong phòng
    assert join(client, world.p2, match).json()["status"] == "OPEN"
    assert join(client, world.p2, match).status_code == 400
    full = join(client, world.p3, match).json()
    assert full["status"] == "FULL" and len(full["participants"]) == 3

    outsider = make_user(db, skill_level=3.5)
    assert join(client, outsider, match).status_code == 400                 # phòng đã đủ người
    assert leave(client, outsider, match).status_code == 400

    reopened = leave(client, world.p3, match).json()
    assert reopened["status"] == "OPEN" and len(reopened["participants"]) == 2
    assert join(client, outsider, match).json()["status"] == "FULL"


def test_a_player_cannot_be_in_two_rooms_at_the_same_time(client, world, clock):
    day, second_court = clock.day(1), world.venue_a.courts[1]
    evening = open_match(client, world.p1, confirmed_booking(client, world.p1, world.court, day, hours=(18, 19)))      # 18-20
    overlapping = open_match(client, world.p2, confirmed_booking(client, world.p2, second_court, day, hours=(19, 20)))  # 19-21
    later = open_match(client, world.p2, confirmed_booking(client, world.p2, second_court, day, hours=(21,)))          # 21-22

    assert join(client, world.p3, evening).status_code == 200
    clash = join(client, world.p3, overlapping)
    assert clash.status_code == 400 and "trùng giờ" in clash.json()["detail"]
    assert join(client, world.p1, overlapping).status_code == 400            # chủ phòng cũng không vào phòng khác trùng giờ
    assert join(client, world.p3, later).status_code == 200                  # phòng liền sau, không trùng giờ

    # Rời phòng (hoặc phòng bị hủy) thì khung giờ đó hết vướng
    assert leave(client, world.p3, evening).status_code == 200
    assert join(client, world.p3, overlapping).status_code == 200

    # Cũng không mở được phòng của riêng mình trùng giờ với phòng đang tham gia
    own = confirmed_booking(client, world.p3, world.court, day, hours=(20,))  # 20-21, trùng phòng 19-21
    assert "trùng giờ" in open_match(client, world.p3, own, expect=400)["detail"]
    assert leave(client, world.p3, overlapping).status_code == 200
    assert open_match(client, world.p3, own)["status"] == "OPEN"


def test_cannot_join_a_match_that_is_over_or_closed(client, db, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18,))
    match = open_match(client, world.p1, booking)
    assert join(client, world.p2, {"id": 9999}).status_code == 404

    clock.set(day, 19, 5)
    assert join(client, world.p2, match).status_code == 400
    match_service.auto_update_expired_matches(db)
    assert join(client, world.p2, match).status_code == 400
    assert leave(client, world.p1, match).status_code == 400


# ---------------------------------------------------------------------------
# Đồng bộ với đơn đặt sân và thời gian
# ---------------------------------------------------------------------------
def test_match_is_cancelled_when_its_booking_is_cancelled(client, db, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    match = open_match(client, world.p1, booking)
    join(client, world.p2, match)

    client.post(f"{BOOKINGS}/{booking['id']}/cancel", headers=auth(world.p1),
                json={"bank_account": "1", "bank_name": "MB", "account_holder": "A"})
    assert status_of(db, match) == "CANCELLED"


def test_match_is_cancelled_when_the_venue_cancels_or_nobody_shows_up(client, db, world, clock):
    day = clock.day(1)
    by_venue = confirmed_booking(client, world.p1, world.court, day, hours=(18,))
    no_show = confirmed_booking(client, world.p2, world.venue_a.courts[1], day, hours=(18,))
    first, second = open_match(client, world.p1, by_venue), open_match(client, world.p2, no_show)

    client.put(f"{BOOKINGS}/{by_venue['id']}/status", json={"status": "CANCELLED"}, headers=auth(world.owner_a))
    assert status_of(db, first) == "CANCELLED"

    clock.set(day, 19, 30)
    booking_service.finalize_past_bookings(db)
    assert status_of(db, second) == "CANCELLED"


def test_match_follows_a_rescheduled_booking(client, db, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18, 19))
    match = open_match(client, world.p1, booking)
    other = world.venue_a.courts[1]

    client.put(f"{BOOKINGS}/staff/{booking['id']}/reschedule", headers=auth(world.staff_a),
               json={"court_id": other.id, "booking_date": clock.day(2).isoformat(), "start_time": "09:00:00"})
    db.expire_all()
    moved = db.get(Match, match["id"])
    assert (moved.court_id, moved.date, moved.start_time.hour, moved.end_time.hour) == (other.id, clock.day(2), 9, 11)


def test_finished_matches_are_completed_when_full_and_cancelled_otherwise(client, db, world, clock):
    day = clock.day(1)
    full = open_match(client, world.p1, confirmed_booking(client, world.p1, world.court, day, hours=(9,)), num_players=2)
    short = open_match(client, world.p2, confirmed_booking(client, world.p2, world.venue_a.courts[1], day, hours=(9,)))
    later = open_match(client, world.p3, confirmed_booking(client, world.p3, world.court, day, hours=(20,)))
    join(client, world.p3, full)

    clock.set(day, 9, 30)
    assert match_service.auto_update_expired_matches(db) == []          # trận đang diễn ra
    clock.set(day, 10, 0)
    updated = {row["id"]: row["status"] for row in match_service.auto_update_expired_matches(db)}
    assert updated == {full["id"]: "COMPLETED", short["id"]: "CANCELLED"}
    assert status_of(db, later) == "OPEN"


# ---------------------------------------------------------------------------
# Danh sách và quyền riêng tư
# ---------------------------------------------------------------------------
def test_public_list_shows_active_matches_without_personal_contact_details(client, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    match = open_match(client, world.p1, booking)
    join(client, world.p2, match)

    public = client.get(MATCHES).json()
    assert [m["id"] for m in public] == [match["id"]]
    dump = json.dumps(public)
    assert "@" not in dump                                      # không lộ email ở bất kỳ trường nào
    assert all(p["phone"] is None for m in public for p in m["participants"])
    assert all(m["compatibility"] is None for m in public)

    def phones(user):
        listed = client.get(MATCHES, headers=auth(user)).json()
        return [p["phone"] for m in listed for p in m["participants"]]

    assert phones(world.p3) == [None, None]                      # người ngoài phòng không thấy số điện thoại
    assert sorted(phones(world.p2)) == ["090000001", "090000002"]  # thành viên thấy số của nhau để liên lạc


def test_my_closed_matches_stay_visible_to_me_only(client, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    match = open_match(client, world.p1, booking)
    join(client, world.p2, match)
    leave(client, world.p1, match)  # hủy phòng

    assert client.get(MATCHES).json() == []
    assert client.get(MATCHES, headers=auth(world.p3)).json() == []
    for member in (world.p1, world.p2):
        assert [m["status"] for m in client.get(MATCHES, headers=auth(member)).json()] == ["CANCELLED"]


def test_logged_in_player_gets_model_compatibility_for_each_match(client, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    match = open_match(client, world.p1, booking)

    [seen] = client.get(MATCHES, headers=auth(world.p2), params={"latitude": 10.78, "longitude": 106.70}).json()
    assert seen["id"] == match["id"] and 0 <= seen["compatibility"] <= 100


def test_only_rooms_the_model_rates_highly_are_recommended(client, db, world, clock):
    """Phòng được "mô hình đề xuất" khi độ phù hợp đạt ngưỡng; người lệch trình độ xa không được đề xuất phòng đó."""
    from app.core.matching_policy import RECOMMEND_MIN_COMPATIBILITY

    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    open_match(client, world.p1, booking)
    far_level = make_user(db, "PLAYER", "pro@example.com", skill_level=5.5, latitude=10.78, longitude=106.70)

    [for_peer] = client.get(MATCHES, headers=auth(world.p2)).json()        # cùng trình độ 3.5, cùng khu vực
    assert for_peer["compatibility"] >= RECOMMEND_MIN_COMPATIBILITY and for_peer["is_recommended"] is True

    [for_pro] = client.get(MATCHES, headers=auth(far_level)).json()        # chênh 2.0 điểm trình độ
    assert for_pro["compatibility"] < RECOMMEND_MIN_COMPATIBILITY and for_pro["is_recommended"] is False

    [public] = client.get(MATCHES).json()                                  # chưa đăng nhập: không có điểm, không đề xuất
    assert public["compatibility"] is None and public["is_recommended"] is False

    [mine] = client.get(MATCHES, headers=auth(world.p1)).json()            # phòng chỉ có mình: không có ai để so
    assert mine["compatibility"] is None and mine["is_recommended"] is False


def test_room_hours_map_onto_the_free_time_grid_of_the_profile():
    from app.core.matching_policy import PERIOD_HOURS, fits_free_time, slots_of_window
    from app.ml.features import AVAILABILITY_SLOTS, PERIODS

    assert [period for period, _, _ in PERIOD_HOURS] == PERIODS                            # cùng ba buổi với lưới khung rảnh của hồ sơ
    monday = date(2026, 10, 12)
    assert slots_of_window(monday, time(5, 0), time(6, 0)) == ["mon_morning"]
    assert slots_of_window(monday, time(11, 0), time(12, 0)) == ["mon_morning"]           # kết thúc đúng 12:00 vẫn là buổi sáng
    assert slots_of_window(monday, time(12, 0), time(13, 0)) == ["mon_afternoon"]
    assert slots_of_window(monday, time(11, 30), time(12, 30)) == ["mon_morning", "mon_afternoon"]
    assert slots_of_window(monday, time(16, 0), time(18, 0)) == ["mon_afternoon", "mon_evening"]
    assert slots_of_window(monday, time(17, 0), time(19, 0)) == ["mon_evening"]
    assert slots_of_window(date(2026, 10, 18), time(22, 0), time(23, 0)) == ["sun_evening"]
    every_hour = {slot for offset in range(7) for hour in range(23)
                  for slot in slots_of_window(monday + timedelta(days=offset), time(hour, 0), time(hour + 1, 0))}
    assert every_hour == set(AVAILABILITY_SLOTS)                                           # giờ nào trong tuần cũng rơi vào một ô của lưới

    assert fits_free_time([], monday, time(18, 0), time(19, 0)) is None                    # chưa khai khung rảnh nào
    assert fits_free_time(["mon_evening"], monday, time(18, 0), time(19, 0)) is True
    assert fits_free_time(["mon_evening"], monday, time(16, 0), time(18, 0)) is False      # lấn sang buổi chiều
    assert fits_free_time(["tue_evening", "mon_morning"], monday, time(18, 0), time(19, 0)) is False


def test_a_room_outside_the_viewers_free_time_is_not_recommended(client, db, world, clock):
    """Phòng đủ điểm phù hợp chỉ được đề xuất khi giờ chơi nằm trọn trong khung rảnh người xem đã khai."""
    from app.core.matching_policy import RECOMMEND_MIN_COMPATIBILITY
    from app.ml.features import DAYS

    day = clock.day(1)
    weekday, next_weekday = DAYS[day.weekday()], DAYS[(day.weekday() + 1) % 7]
    evening = open_match(client, world.p1, confirmed_booking(client, world.p1, world.court, day, hours=(18,)))                 # 18:00 - 19:00
    across = open_match(client, world.p3, confirmed_booking(client, world.p3, world.venue_a.courts[1], day, hours=(16, 17)))  # 16:00 - 18:00

    def viewer(*slots):
        return make_user(db, "PLAYER", skill_level=3.5, latitude=10.78, longitude=106.70, availability=json.dumps(list(slots)))

    def seen(user):
        """Với từng phòng: (nằm trong giờ rảnh?, được đề xuất?, đủ điểm phù hợp?)."""
        return {m["id"]: (m["fits_free_time"], m["is_recommended"], m["compatibility"] >= RECOMMEND_MIN_COMPATIBILITY)
                for m in client.get(MATCHES, headers=auth(user)).json()}

    # Rảnh buổi tối hôm đó: phòng 18:00 nằm trọn trong giờ rảnh, phòng 16:00 - 18:00 lấn sang buổi chiều thì không
    assert seen(viewer(f"{weekday}_evening")) == {evening["id"]: (True, True, True), across["id"]: (False, False, True)}
    # Rảnh cả chiều lẫn tối: cả hai phòng đều được đề xuất
    assert set(seen(viewer(f"{weekday}_afternoon", f"{weekday}_evening")).values()) == {(True, True, True)}
    # Chỉ rảnh buổi sáng, hoặc rảnh buổi tối của ngày khác: đủ điểm phù hợp nhưng không được đề xuất
    for slots in ((f"{weekday}_morning",), (f"{next_weekday}_evening",)):
        assert set(seen(viewer(*slots)).values()) == {(False, False, True)}
    # Chưa khai khung rảnh nào: không có căn cứ để loại phòng, chỉ xét độ phù hợp
    assert set(seen(world.p2).values()) == {(None, True, True)}
    assert {m["fits_free_time"] for m in client.get(MATCHES).json()} == {None}             # chưa đăng nhập


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
def test_admin_match_management(client, db, world, clock):
    admin, day = auth(world.admin), clock.day(1)
    payload = {"venue_id": world.venue_a.id, "court_id": world.court.id, "date": day.isoformat(),
               "start_time": "18:00:00", "end_time": "20:00:00", "num_players": 2, "creator_id": world.p1.id}

    assert client.post(f"{MATCHES}/admin/create", json=payload, headers=auth(world.owner_a)).status_code == 403
    assert client.post(f"{MATCHES}/admin/create", json={**payload, "end_time": "17:00:00"}, headers=admin).status_code == 422
    wrong_court = {**payload, "court_id": world.venue_b.courts[0].id}
    assert client.post(f"{MATCHES}/admin/create", json=wrong_court, headers=admin).status_code == 400

    match = client.post(f"{MATCHES}/admin/create", json=payload, headers=admin).json()
    path = f"{MATCHES}/admin/{match['id']}"
    assert match["participants"][0]["phone"] == "090000001"  # admin thấy số điện thoại để hỗ trợ

    added = client.post(f"{path}/participants", json={"user_id": world.p2.id}, headers=admin).json()
    assert added["status"] == "FULL"
    assert client.post(f"{path}/participants", json={"user_id": world.p2.id}, headers=admin).status_code == 400
    assert client.post(f"{path}/participants", json={"user_id": world.p3.id}, headers=admin).status_code == 400
    assert client.delete(f"{path}/participants/{world.p2.id}", headers=admin).json()["status"] == "OPEN"
    assert client.delete(f"{path}/participants/{world.p2.id}", headers=admin).status_code == 404

    assert client.put(f"{path}/status", json={"status": "CANCELLED"}, headers=admin).json()["status"] == "CANCELLED"
    assert client.put(f"{path}/status", json={"status": "WHATEVER"}, headers=admin).status_code == 422
    assert client.put(path, json={"end_time": "17:00:00"}, headers=admin).status_code == 400
    assert len(client.get(f"{MATCHES}/admin/all", headers=admin, params={"status": "CANCELLED"}).json()) == 1
    assert client.get(f"{MATCHES}/admin/all", headers=admin, params={"status": "OPEN"}).json() == []
    assert client.delete(path, headers=admin).status_code == 200
    assert db.query(Match).count() == 0
