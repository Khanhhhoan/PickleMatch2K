"""Đơn tạo tại quầy, khách vãng lai, dời lịch và số liệu doanh thu lấy từ sổ giao dịch."""
import pytest

from app.models.booking import Booking
from app.models.payment import PaymentTransaction
from helpers import auth, confirmed_booking, create_booking, sepay, slot

BOOKINGS = "/api/v1/bookings"


def desk_payload(court, day, start="09:00:00", end="10:00:00", **extra):
    return {"court_id": court.id, "date": day.isoformat(), "start_time": start, "end_time": end, **extra}


def desk(client, user, payload, path="desk"):
    return client.post(f"{BOOKINGS}/{path}", json=payload, headers=auth(user))


# ---------------------------------------------------------------------------
# Tạo đơn tại quầy
# ---------------------------------------------------------------------------
def test_desk_booking_paid_in_cash_is_confirmed_immediately(client, db, world, clock):
    payload = desk_payload(world.court, clock.day(1), "09:00:00", "11:00:00",
                           customer_name="Anh Bình", customer_phone="0911222333", payment_method="CASH")
    response = desk(client, world.staff_a, payload)
    assert response.status_code == 200, response.text
    body = response.json()

    assert (body["source"], body["status"], body["payment_status"]) == ("DESK", "CONFIRMED", "FULLY_PAID")
    assert body["total_price"] == body["paid_amount"] == 200000 and body["expires_at"] is None
    assert len(body["details"]) == 2
    # Thông tin khách vãng lai, không lộ email của nhân viên tạo đơn
    assert (body["user_name"], body["user_phone"], body["user_email"]) == ("Anh Bình", "0911222333", "")

    txn = db.query(PaymentTransaction).filter_by(booking_id=body["id"]).one()
    assert (txn.method, txn.amount_in, txn.created_by_id) == ("CASH", 200000, world.staff_a.id)


@pytest.mark.parametrize("method, payment_status, paid, ledger_rows", [
    ("FULLY_PAID", "FULLY_PAID", 100000, 1),
    ("BANK_TRANSFER", "FULLY_PAID", 100000, 1),
    ("DEPOSIT_PAID", "DEPOSIT_PAID", 50000, 1),
    ("UNPAID", "UNPAID", 0, 0),
])
def test_desk_payment_options(client, db, world, clock, method, payment_status, paid, ledger_rows):
    body = desk(client, world.owner_a, desk_payload(world.court, clock.day(1), payment_method=method)).json()
    assert (body["status"], body["payment_status"], body["paid_amount"]) == ("CONFIRMED", payment_status, paid)
    assert db.query(PaymentTransaction).count() == ledger_rows
    assert body["user_name"] == "Khách tại quầy"


def test_staff_portal_field_names_are_accepted(client, world, clock):
    payload = {"court_id": world.court.id, "booking_date": clock.day(1).isoformat(), "start_time": "09:00",
               "end_time": "10:00", "guest_name": "Chị Lan", "guest_phone": "", "price": "", "payment_method": "UNPAID"}
    body = desk(client, world.staff_a, payload).json()
    assert body["user_name"] == "Chị Lan" and body["user_phone"] == "" and body["total_price"] == 100000


def test_agreed_price_is_split_across_slots_exactly(client, world, clock):
    payload = desk_payload(world.court, clock.day(1), "09:00:00", "12:00:00", price=250001, payment_method="UNPAID")
    body = desk(client, world.staff_a, payload).json()
    prices = [d["price"] for d in body["details"]]
    assert body["total_price"] == 250001 and sum(prices) == 250001 and len(prices) == 3
    assert body["deposit_amount"] == 125000


def test_desk_booking_validation(client, world, clock):
    day = clock.day(1)
    assert desk(client, world.staff_a, desk_payload(world.court, day, "09:00:00", "10:30:00")).status_code == 400
    assert desk(client, world.staff_a, desk_payload(world.court, day, "10:00:00", "09:00:00")).status_code == 400
    assert desk(client, world.staff_a, desk_payload(world.court, day, "03:00:00", "04:00:00")).status_code == 400
    assert desk(client, world.staff_a, desk_payload(world.court, day, payment_method="FREE")).status_code == 422

    create_booking(client, world.p1, world.court, day, hours=(18,))
    assert desk(client, world.staff_a, desk_payload(world.court, day, "17:00:00", "19:00:00")).status_code == 409


def test_only_staff_of_the_venue_can_create_desk_bookings(client, world, clock):
    payload = desk_payload(world.court, clock.day(1))
    assert desk(client, world.p1, payload).status_code == 403
    assert desk(client, world.staff_b, payload).status_code == 403
    assert desk(client, world.owner_b, payload).status_code == 403
    assert desk(client, world.admin, payload).status_code == 200


def test_walk_in_starts_checked_in_and_may_use_a_slot_in_progress(client, world, clock):
    clock.set(clock.today, 9, 20)
    today = clock.today
    running = desk(client, world.staff_a, desk_payload(world.court, today, "09:00:00", "10:00:00"), path="staff/walkin")
    assert running.status_code == 200, running.text
    assert running.json()["status"] == "CHECKED_IN" and running.json()["checked_in_at"]

    finished = desk(client, world.staff_a, desk_payload(world.court, today, "08:00:00", "09:00:00"), path="staff/walkin")
    assert finished.status_code == 400

    tomorrow = desk(client, world.staff_a, desk_payload(world.court, clock.day(1)), path="staff/walkin")
    assert tomorrow.json()["status"] == "CONFIRMED"


def test_online_customer_cannot_take_a_slot_in_progress(client, world, clock):
    clock.set(clock.today, 9, 20)
    assert client.post(BOOKINGS, json={"details": [slot(world.court, clock.today, 9)]},
                       headers=auth(world.p1)).status_code == 400


def test_desk_bookings_do_not_appear_in_a_players_history(client, world, clock):
    desk(client, world.staff_a, desk_payload(world.court, clock.day(1)))
    assert client.get(f"{BOOKINGS}/me", headers=auth(world.staff_a)).json() == []
    assert len(client.get(f"{BOOKINGS}/owner/list", headers=auth(world.staff_a)).json()) == 1


# ---------------------------------------------------------------------------
# Dời lịch
# ---------------------------------------------------------------------------
def reschedule(client, user, booking, **body):
    return client.put(f"{BOOKINGS}/staff/{booking['id']}/reschedule", json=body, headers=auth(user))


def test_reschedule_moves_slots_and_keeps_the_agreed_price(client, db, world, clock):
    day, new_day = clock.day(1), clock.day(2)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18, 19))  # 300.000đ giờ cao điểm
    other_court = world.venue_a.courts[1]

    response = reschedule(client, world.staff_a, booking, court_id=other_court.id,
                          booking_date=new_day.isoformat(), start_time="09:00:00")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [(d["court_id"], d["date"], d["start_time"]) for d in body["details"]] == [
        (other_court.id, new_day.isoformat(), "09:00:00"), (other_court.id, new_day.isoformat(), "10:00:00")]
    assert body["total_price"] == 300000 and sum(d["price"] for d in body["details"]) == 300000
    assert body["paid_amount"] == 150000 and body["status"] == "CONFIRMED"

    # Khung cũ đã trống, khung mới đã bị chiếm
    assert client.post(BOOKINGS, json={"details": [slot(world.court, day, 18)]}, headers=auth(world.p2)).status_code == 200
    assert client.post(BOOKINGS, json={"details": [slot(other_court, new_day, 10)]}, headers=auth(world.p2)).status_code == 409


def test_reschedule_into_an_occupied_slot_keeps_the_original_booking(client, db, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18,))
    create_booking(client, world.p2, world.court, day, hours=(20,))

    assert reschedule(client, world.staff_a, booking, start_time="20:00:00").status_code == 409
    db.expire_all()
    stored = db.get(Booking, booking["id"])
    assert [(d.start_time.hour, d.is_active) for d in stored.details] == [(18, True)]


def test_reschedule_rules(client, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18,))

    assert reschedule(client, world.staff_a, booking, court_id=world.venue_b.courts[0].id).status_code == 400
    assert reschedule(client, world.staff_a, booking, date=clock.today.isoformat(), start_time="07:00:00").status_code == 400
    assert reschedule(client, world.staff_a, booking, start_time="22:30:00").status_code == 400
    assert reschedule(client, world.staff_b, booking, start_time="20:00:00").status_code == 403
    assert reschedule(client, world.p1, booking, start_time="20:00:00").status_code == 403
    # Tên trường "date" của cổng chủ sân cũng được chấp nhận
    assert reschedule(client, world.owner_a, booking, date=clock.day(3).isoformat()).json()["details"][0]["date"] == (
        clock.day(3).isoformat())

    clock.set(clock.day(3), 17, 55)
    client.post(f"{BOOKINGS}/{booking['id']}/checkin", headers=auth(world.staff_a))
    assert reschedule(client, world.staff_a, booking, start_time="20:00:00").status_code == 400


# ---------------------------------------------------------------------------
# Thống kê từ sổ giao dịch
# ---------------------------------------------------------------------------
def test_owner_stats_come_from_the_ledger(client, world, clock):
    day = clock.day(1)
    played = confirmed_booking(client, world.p1, world.court, day, hours=(9,))               # cọc 50k chuyển khoản
    refunded = confirmed_booking(client, world.p2, world.venue_a.courts[1], day, hours=(9,))  # cọc 50k rồi hủy
    desk(client, world.staff_a, desk_payload(world.court, day, "11:00:00", "12:00:00", payment_method="CASH"))  # 100k
    create_booking(client, world.p3, world.court, day, hours=(14,))                           # chưa trả đồng nào
    confirmed_booking(client, world.p3, world.venue_b.courts[0], day, hours=(9,))             # cụm sân khác

    client.post(f"{BOOKINGS}/{refunded['id']}/cancel", headers=auth(world.p2),
                json={"bank_account": "1", "bank_name": "MB", "account_holder": "B"})
    client.post(f"{BOOKINGS}/{refunded['id']}/confirm-refund", headers=auth(world.owner_a))
    clock.set(day, 8, 55)
    client.post(f"{BOOKINGS}/{played['id']}/checkin", headers=auth(world.staff_a))             # thu nốt 50k tiền mặt
    client.put(f"{BOOKINGS}/{played['id']}/status", json={"status": "COMPLETED"}, headers=auth(world.staff_a))

    stats = client.get(f"{BOOKINGS}/owner/stats", headers=auth(world.owner_a)).json()
    assert stats["collected_amount"] == 50000 + 50000 + 100000 + 50000
    assert stats["refunded_amount"] == 50000
    assert stats["total_revenue"] == 200000
    assert stats["deposit_collected"] == 200000  # 2 khoản cọc online + khoản thu tại quầy khi tạo đơn
    assert (stats["total_bookings"], stats["completed_bookings"], stats["pending_bookings"]) == (4, 1, 1)
    assert stats["pending_refunds"] == 0 and stats["total_courts"] == 2 and stats["venue_names"] == ["Sân A"]

    other = client.get(f"{BOOKINGS}/owner/stats", headers=auth(world.owner_b)).json()
    assert (other["collected_amount"], other["total_bookings"]) == (100000, 1)
    everything = client.get(f"{BOOKINGS}/owner/stats", headers=auth(world.admin)).json()
    assert everything["collected_amount"] == 350000 and everything["total_bookings"] == 5


def test_staff_shift_stats_cover_only_today_at_their_venue(client, world, clock):
    today = clock.today
    desk(client, world.staff_a, desk_payload(world.court, today, "09:00:00", "10:00:00", payment_method="CASH"),
         path="staff/walkin")                                                           # 100k tiền mặt, đã vào sân
    online = create_booking(client, world.p1, world.court, today, hours=(18,))
    sepay(client, online["booking_code"], online["deposit_amount"])                     # 75k chuyển khoản, chờ đến
    confirmed_booking(client, world.p2, world.venue_b.courts[0], today, hours=(18,))    # cụm sân khác

    stats = client.get(f"{BOOKINGS}/staff/stats", headers=auth(world.staff_a)).json()
    assert stats["venue_name"] == "Sân A" and stats["today_date"] == today.isoformat()
    assert stats["today_cash_collected"] == 100000
    assert stats["today_deposit_online"] == 75000
    assert stats["today_revenue"] == 175000
    assert (stats["today_total_bookings"], stats["today_completed_bookings"], stats["today_pending_bookings"]) == (2, 1, 1)
    assert stats["today_courts_count"] == 2
