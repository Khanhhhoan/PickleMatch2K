"""Tạo đơn, kiểm tra đầu vào, hết hạn giữ chỗ, check-in/hoàn tất và ràng buộc chống đặt trùng ở CSDL."""
from datetime import datetime, time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.core import booking_policy as policy
from app.models.booking import Booking, BookingDetail
from app.models.payment import PaymentTransaction
from app.services import booking_service
from helpers import auth, confirmed_booking, create_booking, get_booking, make_user, make_venue, pay_deposit, slot

BOOKINGS = "/api/v1/bookings"


def post_booking(client, user, details):
    return client.post(BOOKINGS, json={"details": details}, headers=auth(user))


# ---------------------------------------------------------------------------
# Tạo đơn
# ---------------------------------------------------------------------------
def test_new_booking_is_pending_with_half_deposit_and_15_minute_deadline(client, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(9, 10))

    assert booking["status"] == "PENDING" and booking["payment_status"] == "UNPAID"
    assert booking["source"] == "ONLINE" and booking["booking_code"] == "PK2K000001"
    assert booking["total_price"] == 200000
    assert booking["deposit_amount"] == 100000
    assert booking["paid_amount"] == 0 and booking["remaining_amount"] == 200000
    assert [d["price"] for d in booking["details"]] == [100000, 100000]
    assert datetime.fromisoformat(booking["expires_at"]) == clock.moment + policy.PENDING_PAYMENT_TTL


def test_booking_codes_are_sequential(client, world, clock):
    codes = [create_booking(client, world.p1, world.court, clock.day(1), hours=(h,))["booking_code"] for h in (9, 10, 11)]
    assert codes == ["PK2K000001", "PK2K000002", "PK2K000003"]


def test_duplicate_slots_in_one_request_are_collapsed(client, world, clock):
    same = slot(world.court, clock.day(1), 9)
    response = post_booking(client, world.p1, [same, same])
    assert response.status_code == 200
    assert len(response.json()["details"]) == 1 and response.json()["total_price"] == 100000


def test_anonymous_user_cannot_book(client, world, clock):
    assert client.post(BOOKINGS, json={"details": [slot(world.court, clock.day(1), 9)]}).status_code == 401


# ---------------------------------------------------------------------------
# Kiểm tra đầu vào
# ---------------------------------------------------------------------------
def test_cannot_book_a_slot_that_already_started(client, world, clock):
    today = clock.today  # đồng hồ đang ở 08:00
    assert post_booking(client, world.p1, [slot(world.court, today, 7)]).status_code == 400
    assert post_booking(client, world.p1, [slot(world.court, today, 8)]).status_code == 400
    assert post_booking(client, world.p1, [slot(world.court, today, 9)]).status_code == 200


def test_slot_must_be_on_the_hourly_grid_inside_opening_hours(client, world, clock):
    day = clock.day(1)
    off_grid = slot(world.court, day, 18, 30)
    two_hours_as_one = {**slot(world.court, day, 18), "end_time": "20:00:00"}
    before_open = slot(world.court, day, 4)
    after_close = slot(world.court, day, 23)
    for bad in (off_grid, two_hours_as_one, before_open, after_close):
        assert post_booking(client, world.p1, [bad]).status_code == 400, bad
    assert post_booking(client, world.p1, [slot(world.court, day, 22)]).status_code == 200  # khung cuối 22:00-23:00


def test_grid_follows_a_half_hour_opening_time(client, db, world, clock):
    venue = make_venue(db, make_user(db, "OWNER"), open_time=time(5, 30), close_time=time(23, 0))
    court = venue.courts[0]
    assert post_booking(client, world.p1, [slot(court, clock.day(1), 18)]).status_code == 400
    assert post_booking(client, world.p1, [slot(court, clock.day(1), 18, 30)]).status_code == 200
    # 22:30-23:30 vượt giờ đóng cửa nên không có trên lưới
    assert post_booking(client, world.p1, [slot(court, clock.day(1), 22, 30)]).status_code == 400


def test_cannot_book_on_a_day_the_venue_is_closed(client, db, world, clock):
    day = clock.day(2)
    venue = make_venue(db, make_user(db, "OWNER"), closed_days=(day.weekday(),))
    assert post_booking(client, world.p1, [slot(venue.courts[0], day, 9)]).status_code == 400
    assert post_booking(client, world.p1, [slot(venue.courts[0], clock.day(3), 9)]).status_code == 200


def test_advance_booking_window(client, world, clock):
    assert post_booking(client, world.p1, [slot(world.court, clock.day(policy.MAX_ADVANCE_DAYS + 1), 9)]).status_code == 400
    assert post_booking(client, world.p1, [slot(world.court, clock.day(policy.MAX_ADVANCE_DAYS), 9)]).status_code == 200


def test_request_size_limits(client, world, clock):
    assert post_booking(client, world.p1, []).status_code == 422
    too_many = [slot(world.court, clock.day(1), h) for h in range(5, 5 + policy.MAX_SLOTS_PER_BOOKING + 1)]
    assert post_booking(client, world.p1, too_many).status_code == 422
    assert post_booking(client, world.p1, too_many[:policy.MAX_SLOTS_PER_BOOKING]).status_code == 200


def test_one_booking_cannot_span_two_venues(client, world, clock):
    details = [slot(world.venue_a.courts[0], clock.day(1), 9), slot(world.venue_b.courts[0], clock.day(1), 9)]
    assert post_booking(client, world.p1, details).status_code == 400


def test_unknown_or_unavailable_court_and_venue(client, db, world, clock):
    ghost = {**slot(world.court, clock.day(1), 9), "court_id": 99999}
    assert post_booking(client, world.p1, [ghost]).status_code == 400

    world.venue_a.courts[1].status = "MAINTENANCE"
    world.venue_b.status = "MAINTENANCE"
    db.commit()
    assert post_booking(client, world.p1, [slot(world.venue_a.courts[1], clock.day(1), 9)]).status_code == 400
    assert post_booking(client, world.p1, [slot(world.venue_b.courts[0], clock.day(1), 9)]).status_code == 400


# ---------------------------------------------------------------------------
# Chống đặt trùng
# ---------------------------------------------------------------------------
def test_second_booking_of_the_same_slot_is_rejected(client, world, clock):
    day = clock.day(1)
    create_booking(client, world.p1, world.court, day, hours=(18, 19))

    assert post_booking(client, world.p2, [slot(world.court, day, 19)]).status_code == 409
    assert post_booking(client, world.p2, [slot(world.court, day, 17), slot(world.court, day, 18)]).status_code == 409
    # Sân khác cùng giờ và khung liền kề vẫn đặt được
    assert post_booking(client, world.p2, [slot(world.venue_a.courts[1], day, 18)]).status_code == 200
    assert post_booking(client, world.p2, [slot(world.court, day, 20)]).status_code == 200


def test_rejected_multi_slot_booking_leaves_no_partial_rows(client, db, world, clock):
    day = clock.day(1)
    create_booking(client, world.p1, world.court, day, hours=(19,))
    assert post_booking(client, world.p2, [slot(world.court, day, 18), slot(world.court, day, 19)]).status_code == 409
    assert db.query(Booking).count() == 1 and db.query(BookingDetail).count() == 1
    assert post_booking(client, world.p2, [slot(world.court, day, 18)]).status_code == 200


def test_database_rejects_overlapping_active_slots_even_if_the_application_check_is_bypassed(db, client, world, clock):
    day = clock.day(1)
    booking = create_booking(client, world.p1, world.court, day, hours=(18,))

    def insert(start: time, end: time, active: bool = True):
        db.add(BookingDetail(booking_id=booking["id"], court_id=world.court.id, date=day,
                             start_time=start, end_time=end, price=1, is_active=active))
        db.flush()

    for start, end in [(time(18, 0), time(19, 0)), (time(18, 30), time(19, 30)), (time(17, 30), time(18, 30))]:
        with pytest.raises(IntegrityError):
            insert(start, end)
        db.rollback()

    with pytest.raises(IntegrityError):
        insert(time(20, 0), time(20, 0))  # giờ kết thúc phải sau giờ bắt đầu
    db.rollback()

    insert(time(18, 0), time(19, 0), active=False)  # dòng đã trả slot không tính là trùng
    insert(time(19, 0), time(20, 0))                # khung liền kề hợp lệ
    db.rollback()


# ---------------------------------------------------------------------------
# Hết hạn giữ chỗ
# ---------------------------------------------------------------------------
def test_unpaid_booking_expires_after_15_minutes_and_releases_the_slot(client, db, world, clock):
    day = clock.day(1)
    booking = create_booking(client, world.p1, world.court, day, hours=(18,))

    clock.advance(minutes=14)
    assert booking_service.expire_stale_pending(db) == []
    assert post_booking(client, world.p2, [slot(world.court, day, 18)]).status_code == 409

    clock.advance(minutes=2)
    assert booking_service.expire_stale_pending(db) == [booking["id"]]
    db.expire_all()
    stored = db.get(Booking, booking["id"])
    assert stored.status == "EXPIRED" and stored.expires_at is None
    assert all(not d.is_active for d in stored.details)
    assert post_booking(client, world.p2, [slot(world.court, day, 18)]).status_code == 200


def test_expired_hold_is_released_immediately_without_waiting_for_the_background_job(client, db, world, clock):
    day = clock.day(1)
    booking = create_booking(client, world.p1, world.court, day, hours=(18,))
    clock.advance(minutes=16)

    assert post_booking(client, world.p2, [slot(world.court, day, 18)]).status_code == 200
    db.expire_all()
    assert db.get(Booking, booking["id"]).status == "EXPIRED"


def test_my_bookings_reports_expired_status(client, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    clock.advance(minutes=16)
    assert get_booking(client, world.p1, booking["id"])["status"] == "EXPIRED"


def test_paid_booking_never_expires(client, db, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    assert booking["status"] == "CONFIRMED" and booking["expires_at"] is None
    clock.advance(hours=3)
    assert booking_service.expire_stale_pending(db) == []
    assert get_booking(client, world.p1, booking["id"])["status"] == "CONFIRMED"


def test_pending_booking_limit_per_player(client, world, clock):
    day = clock.day(1)
    pending = [create_booking(client, world.p1, world.court, day, hours=(h,)) for h in (9, 10, 11)]
    assert len(pending) == policy.MAX_PENDING_BOOKINGS_PER_USER
    assert post_booking(client, world.p1, [slot(world.court, day, 12)]).status_code == 429
    assert post_booking(client, world.p2, [slot(world.court, day, 12)]).status_code == 200  # người khác không bị ảnh hưởng

    pay_deposit(client, pending[0])
    assert post_booking(client, world.p1, [slot(world.court, day, 13)]).status_code == 200


# ---------------------------------------------------------------------------
# Check-in và hoàn tất
# ---------------------------------------------------------------------------
def test_checkin_collects_the_balance_in_cash_by_default(client, db, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18, 19))
    assert booking["paid_amount"] == 150000 and booking["remaining_amount"] == 150000  # 2 khung cao điểm x 150k

    clock.set(day, 17, 50)
    response = client.post(f"{BOOKINGS}/{booking['id']}/checkin", headers=auth(world.staff_a))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CHECKED_IN" and body["payment_status"] == "FULLY_PAID"
    assert body["paid_amount"] == 300000 and body["remaining_amount"] == 0 and body["checked_in_at"]

    balance = db.query(PaymentTransaction).filter_by(booking_id=booking["id"], kind="BALANCE").one()
    assert (balance.method, balance.amount_in, balance.created_by_id) == ("CASH", 150000, world.staff_a.id)


def test_checkin_can_defer_payment_and_collect_later(client, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(9,))
    clock.set(day, 8, 55)
    path = f"{BOOKINGS}/{booking['id']}"

    checked_in = client.post(f"{path}/checkin", json={"collected_amount": 0}, headers=auth(world.staff_a)).json()
    assert checked_in["status"] == "CHECKED_IN" and checked_in["payment_status"] == "DEPOSIT_PAID"
    assert checked_in["remaining_amount"] == 50000

    too_much = client.post(f"{path}/collect", json={"amount": 60000}, headers=auth(world.staff_a))
    assert too_much.status_code == 400
    collected = client.post(f"{path}/collect", json={"amount": 50000, "payment_method": "BANK_TRANSFER"},
                            headers=auth(world.staff_a)).json()
    assert collected["payment_status"] == "FULLY_PAID" and collected["remaining_amount"] == 0


def test_checkin_rules(client, world, clock):
    day = clock.day(1)
    pending = create_booking(client, world.p1, world.court, day, hours=(10,))
    confirmed = confirmed_booking(client, world.p2, world.court, day, hours=(18,))

    def checkin(booking):
        return client.post(f"{BOOKINGS}/{booking['id']}/checkin", headers=auth(world.staff_a))

    assert checkin(confirmed).status_code == 400              # chưa tới ngày chơi
    clock.set(day, 9, 0)
    assert checkin(pending).status_code == 400                # chưa cọc
    assert checkin(confirmed).status_code == 200
    assert checkin(confirmed).status_code == 400              # không check-in hai lần

    late = confirmed_booking(client, world.p3, world.venue_a.courts[1], day, hours=(10,))
    clock.set(day, 11, 0)
    assert checkin(late).status_code == 400                   # khung giờ đã kết thúc


def test_past_bookings_are_finalised_as_completed_or_no_show(client, db, world, clock):
    day = clock.day(1)
    arrived = confirmed_booking(client, world.p1, world.court, day, hours=(9, 10))
    absent = confirmed_booking(client, world.p2, world.venue_a.courts[1], day, hours=(9,))
    clock.set(day, 8, 50)
    client.post(f"{BOOKINGS}/{arrived['id']}/checkin", headers=auth(world.staff_a))

    clock.set(day, 10, 30)  # đơn 2 khung của người đã đến vẫn đang diễn ra
    assert booking_service.finalize_past_bookings(db) == [absent["id"]]
    clock.set(day, 11, 1)
    assert booking_service.finalize_past_bookings(db) == [arrived["id"]]

    db.expire_all()
    assert db.get(Booking, arrived["id"]).status == "COMPLETED"
    no_show = db.get(Booking, absent["id"])
    assert no_show.status == "NO_SHOW"
    assert all(d.is_active for d in no_show.details)  # lịch sử chiếm slot được giữ nguyên
    assert booking_service.finalize_past_bookings(db) == []


def test_status_endpoint_only_performs_valid_transitions(client, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(9,))
    path = f"{BOOKINGS}/{booking['id']}/status"
    staff = auth(world.staff_a)

    for invalid in ("PENDING", "CONFIRMED", "EXPIRED", "NO_SHOW", "PAID"):
        assert client.put(path, json={"status": invalid}, headers=staff).status_code == 422

    clock.set(day, 8, 55)
    # "Hoàn tất" trên đơn chưa check-in: hệ thống check-in trước chứ không nhảy cóc trạng thái
    assert client.put(path, json={"status": "COMPLETED"}, headers=staff).json()["status"] == "CHECKED_IN"
    assert client.put(path, json={"status": "COMPLETED"}, headers=staff).json()["status"] == "COMPLETED"
    assert client.put(path, json={"status": "COMPLETED"}, headers=staff).status_code == 400
    assert client.put(path, json={"status": "CANCELLED"}, headers=staff).status_code == 400


def test_timestamps_survive_a_database_roundtrip(client, db, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(9,))
    stored = db.get(Booking, booking["id"])
    assert stored.expires_at - clock.moment == timedelta(minutes=15)
