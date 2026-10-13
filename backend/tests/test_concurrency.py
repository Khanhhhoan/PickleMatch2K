"""
Tranh chấp thật sự: nhiều luồng, mỗi luồng một kết nối CSDL riêng, cùng xuất phát tại một thời điểm.
Kiểm tra kết quả cuối cùng trong CSDL chứ không chỉ mã trả về.
"""
import threading
from typing import Callable, List

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.database import SessionLocal
from app.models.booking import Booking, BookingDetail
from app.models.match import Match, MatchParticipant
from app.models.payment import PaymentTransaction, ShiftClosing
from app.models.user import User
from app.models.venue import Venue
from app.schemas.match import MatchCreate
from app.schemas.payment import SepayWebhookPayload
from app.services import booking_service, ledger, match_service, payment_service, shift_service
from app.services.booking_service import SlotRequest
from helpers import TEST_BANK_ACCOUNT, auth, confirmed_booking, create_booking, make_user, slot
from datetime import time

OVERLAPPING_ACTIVE_SLOTS = text("""
    SELECT count(*) FROM booking_details a JOIN booking_details b
      ON a.id < b.id AND a.court_id = b.court_id AND a.date = b.date
     AND a.is_active AND b.is_active AND a.start_time < b.end_time AND b.start_time < a.end_time
""")


def run_together(count: int, work: Callable[[int], object]) -> List[object]:
    """Chạy `work(i)` trên `count` luồng xuất phát cùng lúc; trả về kết quả hoặc ngoại lệ của từng luồng."""
    barrier = threading.Barrier(count)
    results: List[object] = [None] * count

    def runner(index: int) -> None:
        barrier.wait(timeout=30)
        try:
            results[index] = work(index)
        except Exception as exc:  # ngoại lệ là một kết quả hợp lệ cần được kiểm tra
            results[index] = exc

    threads = [threading.Thread(target=runner, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=120)
    assert not any(t.is_alive() for t in threads), "có luồng bị treo (khả năng deadlock)"
    return results


def conflicts(results) -> List[HTTPException]:
    unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, HTTPException)]
    assert not unexpected, unexpected
    return [r for r in results if isinstance(r, HTTPException)]


def book(user_id: int, slots: List[SlotRequest]) -> int:
    with SessionLocal() as session:
        user = session.get(User, user_id)
        return booking_service.create_booking(session, user=user, slots=slots).id


def test_twenty_players_racing_for_one_slot_produce_exactly_one_booking(db, world, clock):
    players = [make_user(db).id for _ in range(20)]
    day, court_id = clock.day(1), world.court.id
    target = [SlotRequest(court_id, day, time(18, 0), time(19, 0))]

    results = run_together(20, lambda i: book(players[i], target))

    rejected = conflicts(results)
    assert len(rejected) == 19 and {e.status_code for e in rejected} == {409}
    assert db.query(Booking).count() == 1
    assert db.query(BookingDetail).filter_by(is_active=True).count() == 1


def test_overlapping_multi_slot_requests_never_produce_overlapping_bookings(db, world, clock):
    players = [make_user(db).id for _ in range(12)]
    day, court_id = clock.day(1), world.court.id
    early = [SlotRequest(court_id, day, time(18, 0), time(19, 0)), SlotRequest(court_id, day, time(19, 0), time(20, 0))]
    late = [SlotRequest(court_id, day, time(19, 0), time(20, 0)), SlotRequest(court_id, day, time(20, 0), time(21, 0))]

    results = run_together(12, lambda i: book(players[i], early if i % 2 == 0 else late))

    assert len(results) - len(conflicts(results)) == 1  # hai nhóm giẫm nhau ở khung 19:00 nên chỉ một đơn thắng
    assert db.execute(OVERLAPPING_ACTIVE_SLOTS).scalar() == 0
    assert db.query(BookingDetail).filter_by(is_active=True).count() == 2


def test_parallel_bookings_on_different_slots_all_succeed_with_unique_codes(db, world, clock):
    players = [make_user(db).id for _ in range(12)]
    day, court_id = clock.day(1), world.court.id

    results = run_together(12, lambda i: book(players[i], [SlotRequest(court_id, day, time(6 + i, 0), time(7 + i, 0))]))

    assert conflicts(results) == []
    codes = [code for (code,) in db.query(Booking.booking_code).all()]
    assert len(codes) == 12 and len(set(codes)) == 12


def test_the_race_is_also_safe_through_the_http_api(client, db, world, clock):
    players = [make_user(db) for _ in range(10)]
    headers = [auth(p) for p in players]
    payload = {"details": [slot(world.court, clock.day(1), 18)]}
    from app.main import app

    def request(index: int) -> int:
        return TestClient(app).post("/api/v1/bookings", json=payload, headers=headers[index]).status_code

    statuses = run_together(10, request)
    assert sorted(statuses) == [200] + [409] * 9
    assert db.query(BookingDetail).filter_by(is_active=True).count() == 1


def webhook(code: str, amount: float, reference: str) -> dict:
    with SessionLocal() as session:
        return payment_service.process_sepay_webhook(session, SepayWebhookPayload(
            accountNumber=TEST_BANK_ACCOUNT, transferType="in", transferAmount=amount, content=code, referenceCode=reference,
        ))


def test_the_same_bank_transaction_delivered_ten_times_at_once_is_recorded_once(client, db, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))

    results = run_together(10, lambda i: webhook(booking["booking_code"], 75000, "FT-SAME"))

    assert all(isinstance(r, dict) and r["status"] == "success" for r in results), results
    assert sum(1 for r in results if r.get("outcome") == "confirmed") == 1
    assert db.query(PaymentTransaction).count() == 1
    stored = db.get(Booking, booking["id"])
    assert (stored.status, stored.paid_amount) == ("CONFIRMED", 75000)


def test_simultaneous_partial_transfers_are_all_counted(client, db, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))

    results = run_together(6, lambda i: webhook(booking["booking_code"], 20000, f"FT-PART-{i}"))

    assert all(isinstance(r, dict) for r in results), results
    stored = db.get(Booking, booking["id"])
    assert stored.paid_amount == 120000  # không mất khoản nào do ghi đè lẫn nhau
    assert (stored.status, stored.payment_status) == ("CONFIRMED", "DEPOSIT_PAID")
    assert db.query(PaymentTransaction).count() == 6
    assert len({code for (code,) in db.query(PaymentTransaction.transaction_code)}) == 6


def test_a_new_booking_cannot_take_the_slot_while_a_late_deposit_is_being_recorded(client, db, world, clock):
    """
    Đơn vừa quá hạn cọc nhưng tác vụ nền chưa kịp chuyển sang EXPIRED. Đúng lúc tiền cọc của đơn đang được ghi nhận
    (giao dịch đã khóa đơn, chưa commit) thì người khác đặt chính khung giờ đó: người đã trả tiền phải giữ được sân.
    """
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    clock.advance(minutes=16)
    rival = make_user(db).id
    target = [SlotRequest(world.court.id, clock.day(1), time(18, 0), time(19, 0))]
    outcome: List[object] = []

    def rival_books() -> None:
        try:
            outcome.append(book(rival, target))
        except Exception as exc:
            outcome.append(exc)

    with SessionLocal() as paying:
        locked = booking_service.get_booking_or_404(paying, booking["id"], for_update=True)
        ledger.record_transaction(paying, locked, amount=75000, kind="DEPOSIT", reference_number="FT-LATE")
        assert booking_service.apply_payment(paying, locked, 75000) == "confirmed"

        thread = threading.Thread(target=rival_books)
        thread.start()
        thread.join(timeout=3)  # bên đặt mới không được đứng chờ rồi ghi đè lên kết quả thanh toán
        paying.commit()
        thread.join(timeout=30)
        assert not thread.is_alive(), "luồng đặt sân bị treo"

    db.expire_all()
    stored = db.get(Booking, booking["id"])
    assert (stored.status, stored.paid_amount, stored.refund_status) == ("CONFIRMED", 75000, None)
    assert all(d.is_active for d in stored.details)
    assert isinstance(outcome[0], HTTPException) and outcome[0].status_code == 409, outcome
    assert db.query(Booking).count() == 1
    assert db.execute(OVERLAPPING_ACTIVE_SLOTS).scalar() == 0


def test_only_one_player_gets_the_last_seat_in_a_match(client, db, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    match = match_service.create_match(db, world.p1, MatchCreate(booking_id=booking["id"], num_players=2))
    match_id = match.id
    joiners = [make_user(db, skill_level=3.5).id for _ in range(8)]

    def join(index: int) -> int:
        with SessionLocal() as session:
            return match_service.join_match(session, match_id, joiners[index]).id

    results = run_together(8, join)

    assert len(conflicts(results)) == 7
    db.expire_all()
    assert db.query(MatchParticipant).filter_by(match_id=match_id).count() == 2
    assert db.get(Match, match_id).status == "FULL"


def test_one_player_joining_two_overlapping_rooms_at_once_ends_up_in_only_one(client, db, world, clock):
    day = clock.day(1)
    first = confirmed_booking(client, world.p1, world.court, day, hours=(18,))
    second = confirmed_booking(client, world.p2, world.venue_a.courts[1], day, hours=(18,))
    rooms = [
        match_service.create_match(db, world.p1, MatchCreate(booking_id=first["id"])).id,
        match_service.create_match(db, world.p2, MatchCreate(booking_id=second["id"])).id,
    ]
    joiner = world.p3.id

    def join(index: int) -> int:
        with SessionLocal() as session:
            return match_service.join_match(session, rooms[index], joiner).id

    results = run_together(2, join)

    assert len(conflicts(results)) == 1
    assert db.query(MatchParticipant).filter_by(user_id=joiner).count() == 1


def test_cancel_and_payment_racing_on_one_booking_leave_consistent_money(client, db, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    player_id = world.p1.id

    def step(index: int):
        if index == 0:
            return webhook(booking["booking_code"], 75000, "FT-RACE")
        with SessionLocal() as session:
            user = session.get(User, player_id)
            try:
                return booking_service.cancel_by_player(session, booking["id"], user, None).status
            except HTTPException as exc:
                return exc.status_code

    run_together(2, step)

    db.expire_all()
    stored = db.get(Booking, booking["id"])
    assert stored.paid_amount == 75000 and db.query(PaymentTransaction).count() == 1
    if stored.status == "CANCELLED":
        # Hủy trước, tiền đến sau: toàn bộ số tiền phải nằm trong yêu cầu hoàn
        assert (stored.refund_status, stored.refund_amount) == ("PENDING", 75000)
        assert all(not d.is_active for d in stored.details)
    else:
        # Tiền đến trước: đơn được xác nhận, lệnh hủy bị từ chối vì thiếu thông tin nhận tiền hoàn
        assert stored.status == "CONFIRMED" and all(d.is_active for d in stored.details)


def test_closings_sent_at_the_same_moment_count_each_payment_once(client, db, world, clock, monkeypatch):
    from time import sleep

    walk_in = {"court_id": world.court.id, "date": clock.today.isoformat(), "start_time": "09:00:00", "end_time": "10:00:00"}
    assert client.post("/api/v1/bookings/staff/walkin", json=walk_in, headers=auth(world.staff_a)).status_code == 200  # 100k tiền mặt
    venue_id, staff_id = world.venue_a.id, world.staff_a.id

    # Kéo dài khoảng hở giữa lúc đọc số chưa kết và lúc ghi lần kết ca, để các luồng chắc chắn chồng lên nhau
    read_open_figures = shift_service.open_figures

    def slow_open_figures(*args):
        figures = read_open_figures(*args)
        sleep(0.2)
        return figures

    monkeypatch.setattr(shift_service, "open_figures", slow_open_figures)

    def close_shift(_: int) -> float:
        with SessionLocal() as session:
            closing = shift_service.close_shift(
                session, session.get(Venue, venue_id), session.get(User, staff_id), opening_float=0, counted_cash=100000)
            return closing.cash_collected

    results = run_together(8, close_shift)

    # Đúng một lần kết ca nhận khoản 100k; các lần còn lại thấy không còn gì chưa kết
    assert sorted(results) == [0.0] * 7 + [100000.0]
    assert db.query(ShiftClosing).count() == 8
