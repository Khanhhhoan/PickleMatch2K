"""Kết ca tại quầy: đối chiếu tiền mặt đếm được với sổ giao dịch và lưu từng lần kết ca của cụm sân."""
from datetime import datetime

import pytest

from app.models.payment import PaymentTransaction, ShiftClosing
from app.models.user import User
from helpers import auth, confirmed_booking, create_booking, make_user, make_venue, sepay

BOOKINGS = "/api/v1/bookings"
SHIFTS = "/api/v1/payments/shift-closings"


def desk(client, user, court, day, start, end, payment_method="CASH", path="desk"):
    body = {"court_id": court.id, "date": day.isoformat(), "start_time": start, "end_time": end, "payment_method": payment_method}
    response = client.post(f"{BOOKINGS}/{path}", json=body, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def summary(client, user, **params):
    response = client.get(SHIFTS, params=params, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def close(client, user, **body):
    return client.post(SHIFTS, json=body, headers=auth(user))


def money(figures: dict) -> tuple:
    return figures["cash_collected"], figures["transfer_collected"], figures["refunded"]


def instant(value: str) -> datetime:
    """Một thời điểm API trả về (có thể ghi theo UTC hoặc giờ Việt Nam) để so sánh đúng."""
    return datetime.fromisoformat(value)


# ---------------------------------------------------------------------------
# Đối chiếu và lưu
# ---------------------------------------------------------------------------
def test_closing_a_shift_stores_the_ledger_figures_and_the_cash_difference(client, db, world, clock):
    today = clock.today
    desk(client, world.staff_a, world.court, today, "09:00:00", "10:00:00", path="staff/walkin")      # 100k tiền mặt
    online = create_booking(client, world.p1, world.court, today, hours=(18,))
    sepay(client, online["booking_code"], online["deposit_amount"])                                 # 75k chuyển khoản
    confirmed_booking(client, world.p2, world.venue_b.courts[0], today, hours=(18,))                # cụm sân khác: cọc 130k

    before = summary(client, world.staff_a)
    assert (before["venue_name"], before["business_date"]) == ("Sân A", today.isoformat())
    assert money(before) == (100000, 75000, 0) and before["total_collected"] == 175000
    assert before["closings"] == [] and before["last_closed_at"] is None

    response = close(client, world.staff_a, opening_float=500000, counted_cash=590000, note="  Thiếu 10 nghìn tiền lẻ  ")
    assert response.status_code == 200, response.text
    closing = response.json()
    assert money(closing) == (100000, 75000, 0) and closing["total_collected"] == 175000
    assert (closing["opening_float"], closing["counted_cash"]) == (500000, 590000)
    assert (closing["expected_cash"], closing["difference"]) == (600000, -10000)
    assert (closing["business_date"], closing["closed_by_name"]) == (today.isoformat(), world.staff_a.staff_profile.full_name)
    assert closing["note"] == "Thiếu 10 nghìn tiền lẻ"

    stored = db.query(ShiftClosing).one()
    assert (stored.venue_id, stored.closed_by_id, stored.business_date) == (world.venue_a.id, world.staff_a.id, today)

    after = summary(client, world.owner_a)  # chủ sân xem được lần kết ca của nhân viên
    assert money(after) == (0, 0, 0) and after["last_closed_at"] is not None
    assert [c["id"] for c in after["closings"]] == [closing["id"]]
    # Cụm sân khác không thấy và không bị ảnh hưởng
    other = summary(client, world.staff_b)
    assert other["closings"] == [] and money(other) == (0, 130000, 0)


def test_each_closing_covers_only_what_came_after_the_previous_one(client, db, world, clock):
    today = clock.today
    court_1, court_2 = world.venue_a.courts
    desk(client, world.staff_a, court_1, today, "09:00:00", "10:00:00", path="staff/walkin")          # 100k tiền mặt
    cancelled = confirmed_booking(client, world.p2, court_2, clock.day(1), hours=(9,))               # cọc 50k chuyển khoản

    first = close(client, world.staff_a, opening_float=200000, counted_cash=300000).json()
    assert money(first) == (100000, 50000, 0) and first["difference"] == 0

    # Sau lần kết ca thứ nhất: thu cọc tiền mặt, một khoản chuyển khoản tại quầy và một khoản hoàn cho khách
    desk(client, world.owner_a, court_1, today, "11:00:00", "12:00:00", payment_method="DEPOSIT_PAID")       # 50k tiền mặt
    desk(client, world.staff_a, court_1, today, "13:00:00", "14:00:00", payment_method="BANK_TRANSFER")     # 100k chuyển khoản
    client.post(f"{BOOKINGS}/{cancelled['id']}/cancel", headers=auth(world.p2),
                json={"bank_account": "1", "bank_name": "MB", "account_holder": "B"})
    client.post(f"{BOOKINGS}/{cancelled['id']}/confirm-refund", json={"bank_reference": "FT26288SHIFT1"},
                headers=auth(world.staff_a))                                                           # hoàn 50k

    assert money(summary(client, world.staff_a)) == (50000, 100000, 50000)
    second = close(client, world.owner_a, opening_float=200000, counted_cash=260000).json()
    assert money(second) == (50000, 100000, 50000)
    assert (second["expected_cash"], second["difference"]) == (250000, 10000)                          # thừa 10k
    assert second["closed_by_name"] != first["closed_by_name"]

    # Cộng các lần kết ca của ngày ra đúng số của cả ngày trên bảng ca trực
    stats = client.get(f"{BOOKINGS}/staff/stats", headers=auth(world.staff_a)).json()
    closings = summary(client, world.staff_a)["closings"]
    assert [c["id"] for c in closings] == [second["id"], first["id"]]                                  # mới nhất trước
    assert sum(c["cash_collected"] for c in closings) == stats["today_cash_collected"] == 150000
    assert sum(c["transfer_collected"] for c in closings) == stats["today_transfer_collected"] == 150000

    # Không còn gì để kết: lần kết ca thứ ba ghi số 0, không tính lại khoản cũ
    third = close(client, world.staff_a, opening_float=200000, counted_cash=200000).json()
    assert money(third) == (0, 0, 0) and third["difference"] == 0
    assert db.query(ShiftClosing).count() == 3


def test_a_stored_closing_does_not_change_when_money_arrives_later(client, world, clock):
    today = clock.today
    desk(client, world.staff_a, world.court, today, "09:00:00", "10:00:00", path="staff/walkin")
    closing = close(client, world.staff_a, opening_float=0, counted_cash=100000).json()

    desk(client, world.staff_a, world.court, today, "10:00:00", "11:00:00", path="staff/walkin")      # thêm 100k sau khi kết ca
    now = summary(client, world.staff_a)
    assert money(now) == (100000, 0, 0)
    assert now["closings"][0] == closing

    # Hôm đó không kết ca lần nữa: sang hôm sau khoản 100k vẫn còn trong ca đang chạy, không bị bỏ sót,
    # và giờ bắt đầu ca cho thấy ca này kéo từ hôm trước
    clock.set(clock.day(1), 8)
    tomorrow = summary(client, world.staff_a)
    assert money(tomorrow) == (100000, 0, 0)
    assert instant(tomorrow["period_start"]) == instant(closing["closed_at"]) == instant(tomorrow["last_closed_at"])
    assert tomorrow["business_date"] == clock.today.isoformat() and len(tomorrow["closings"]) == 1


def test_a_shift_running_past_midnight_is_closed_once_with_everything_in_it(client, db, world, clock):
    today, tomorrow = clock.today, clock.day(1)
    court_1, court_2 = world.venue_a.courts
    clock.set(today, 19, 55)
    day_shift = close(client, world.staff_a, opening_float=0, counted_cash=0).json()

    clock.set(today, 20, 30)
    desk(client, world.staff_a, court_1, today, "20:00:00", "21:00:00", path="staff/walkin")                  # 150k (cao điểm)
    clock.set(today, 23, 50)
    desk(client, world.staff_a, court_1, tomorrow, "09:00:00", "10:00:00", payment_method="BANK_TRANSFER")    # 100k chuyển khoản
    clock.set(tomorrow, 0, 5)
    desk(client, world.staff_a, court_2, tomorrow, "10:00:00", "11:00:00")                                     # 100k tiền mặt

    clock.set(tomorrow, 0, 15)
    running = summary(client, world.staff_a)
    assert money(running) == (250000, 100000, 0)                 # cả hai phía nửa đêm cùng một ca
    assert instant(running["period_start"]) == instant(day_shift["closed_at"])
    night = close(client, world.staff_a, opening_float=0, counted_cash=250000).json()
    assert money(night) == (250000, 100000, 0) and night["difference"] == 0
    assert instant(night["period_start"]) == instant(day_shift["closed_at"]) and night["business_date"] == tomorrow.isoformat()

    clock.set(tomorrow, 8, 0)
    morning = summary(client, world.staff_a)
    assert money(morning) == (0, 0, 0) and instant(morning["period_start"]) == instant(night["closed_at"])
    # Mỗi giao dịch thuộc đúng một lần kết ca
    payments = db.query(PaymentTransaction).all()
    assert len(payments) == 3 and {p.shift_closing_id for p in payments} == {night["id"]}


def test_money_recorded_after_a_closing_but_dated_before_it_goes_to_the_next_closing(client, db, world, clock):
    today = clock.today
    unpaid = desk(client, world.staff_a, world.court, today, "18:00:00", "19:00:00", payment_method="UNPAID")
    clock.set(today, 9, 30)
    first = close(client, world.staff_a, opening_float=0, counted_cash=0).json()
    assert money(first) == (0, 0, 0)

    # Một khoản ghi sổ có giờ 09:20 nhưng được lưu sau lúc kết ca 09:30 (ví dụ máy chậm): không được rơi mất
    clock.set(today, 9, 20)
    collected = client.post(f"{BOOKINGS}/{unpaid['id']}/collect", json={"amount": 50000, "payment_method": "CASH"},
                            headers=auth(world.staff_a))
    assert collected.status_code == 200, collected.text
    clock.set(today, 10, 0)
    assert money(summary(client, world.staff_a)) == (50000, 0, 0)
    second = close(client, world.staff_a, opening_float=0, counted_cash=50000).json()
    assert money(second) == (50000, 0, 0)
    assert db.query(PaymentTransaction).one().shift_closing_id == second["id"]


@pytest.mark.parametrize("body, expected", [
    ({"opening_float": -1, "counted_cash": 0}, 400),
    ({"opening_float": 0, "counted_cash": -500}, 400),
    ({"opening_float": 100000.5, "counted_cash": 0}, 400),
    ({"opening_float": 0, "counted_cash": 0.25}, 400),
    ({"opening_float": 0, "counted_cash": 5_000_000_000}, 400),
    ({"opening_float": "nhiều", "counted_cash": 0}, 422),
    ({"counted_cash": 0}, 422),
    ({"opening_float": 0, "counted_cash": 0, "note": "x" * 301}, 422),
])
def test_amounts_must_be_whole_and_not_negative(client, db, world, body, expected):
    response = close(client, world.staff_a, **body)
    assert response.status_code == expected, response.text
    if expected == 400:
        assert "số nguyên, không âm" in response.json()["detail"] or "vượt quá" in response.json()["detail"]
    assert db.query(ShiftClosing).count() == 0


# ---------------------------------------------------------------------------
# Phạm vi cụm sân
# ---------------------------------------------------------------------------
def test_a_shift_can_be_closed_only_by_the_people_who_run_the_venue(client, db, world):
    a, b = world.venue_a.id, world.venue_b.id
    amounts = {"opening_float": 0, "counted_cash": 0}

    assert close(client, world.p1, **amounts).status_code == 403
    for outsider in (world.staff_b, world.owner_b):
        assert close(client, outsider, venue_id=a, **amounts).status_code == 403
        assert client.get(SHIFTS, params={"venue_id": a}, headers=auth(outsider)).status_code == 403
    assert db.query(ShiftClosing).count() == 0

    # Không chỉ định cụm sân: nhân viên và chủ sân kết ca cho cụm sân của mình
    assert close(client, world.staff_a, **amounts).json()["venue_id"] == a
    assert close(client, world.owner_b, **amounts).json()["venue_id"] == b
    assert close(client, world.owner_a, venue_id=a, **amounts).status_code == 200
    assert close(client, world.admin, venue_id=b, **amounts).json()["venue_id"] == b
    assert close(client, world.admin, venue_id=999999, **amounts).status_code == 404

    assert {c["venue_id"] for c in summary(client, world.staff_a)["closings"]} == {a}
    assert len(summary(client, world.admin, venue_id=b)["closings"]) == 2

    unassigned = make_user(db, "STAFF", "staff_free@example.com")
    assert close(client, unassigned, **amounts).status_code == 400
    assert client.get(SHIFTS, headers=auth(unassigned)).status_code == 400


def test_an_owner_with_several_venues_chooses_which_one_to_close(client, db, world, clock):
    second = make_venue(db, world.owner_a, name="Sân A2")
    desk(client, world.owner_a, second.courts[0], clock.today, "09:00:00", "10:00:00", path="staff/walkin")  # 100k ở Sân A2

    assert money(summary(client, world.owner_a)) == (0, 0, 0)                      # mặc định: cụm sân đầu tiên
    assert money(summary(client, world.owner_a, venue_id=second.id)) == (100000, 0, 0)
    closing = close(client, world.owner_a, venue_id=second.id, opening_float=0, counted_cash=100000).json()
    assert (closing["venue_id"], closing["cash_collected"]) == (second.id, 100000)
    assert summary(client, world.owner_a)["closings"] == []


# ---------------------------------------------------------------------------
# Giữ lịch sử
# ---------------------------------------------------------------------------
def test_an_account_that_closed_a_shift_is_locked_instead_of_deleted(client, db, world):
    assert close(client, world.staff_a, opening_float=0, counted_cash=0).status_code == 200
    outcome = client.delete(f"/api/v1/users/admin/users/{world.staff_a.id}", headers=auth(world.admin)).json()
    assert outcome["status"] == "deactivated"
    db.expire_all()
    assert db.get(User, world.staff_a.id).is_active is False and db.query(ShiftClosing).count() == 1


def test_deleting_an_unused_venue_removes_its_empty_closings(client, db, world):
    spare = make_venue(db, world.owner_a, name="Sân chưa dùng")
    assert close(client, world.owner_a, venue_id=spare.id, opening_float=0, counted_cash=0).status_code == 200
    assert close(client, world.staff_a, opening_float=0, counted_cash=0).status_code == 200

    assert client.delete(f"/api/v1/venues/admin/{spare.id}", headers=auth(world.admin)).status_code == 200
    db.expire_all()
    assert [c.venue_id for c in db.query(ShiftClosing).all()] == [world.venue_a.id]
