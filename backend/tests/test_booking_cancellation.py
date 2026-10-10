"""Chính sách hủy theo mốc 12 giờ / 6 giờ, hoàn tiền và việc trả lại khung giờ."""
import pytest

from app.models.booking import Booking
from app.models.payment import PaymentTransaction
from app.services import booking_service
from helpers import auth, confirmed_booking, create_booking, sepay, slot

BOOKINGS = "/api/v1/bookings"
BANK = {"bank_account": "0123456789", "bank_name": "Vietcombank", "account_holder": "NGUYEN VAN A"}


def preview(client, user, booking):
    response = client.get(f"{BOOKINGS}/{booking['id']}/cancel-preview", headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def cancel(client, user, booking, body=None):
    return client.post(f"{BOOKINGS}/{booking['id']}/cancel", json=body, headers=auth(user))


# ---------------------------------------------------------------------------
# Mức hoàn theo thời điểm hủy (khung giờ chơi: 18:00 ngày mai, cọc 75.000đ)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("hour, minute, tier, refund", [
    (6, 0, "FULL_REFUND", 75000),       # đúng 12 tiếng trước giờ chơi
    (5, 59, "FULL_REFUND", 75000),
    (6, 1, "RESCHEDULE_ONLY", 0),       # 11 giờ 59 phút
    (12, 0, "RESCHEDULE_ONLY", 0),      # đúng 6 tiếng
    (12, 1, "NO_REFUND", 0),
    (17, 59, "NO_REFUND", 0),
])
def test_cancellation_tiers_on_the_day_of_play(client, world, clock, hour, minute, tier, refund):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18,))
    clock.set(day, hour, minute)

    result = preview(client, world.p1, booking)
    assert result["can_cancel"] is True
    assert (result["tier"], result["refund_amount"], result["paid_amount"]) == (tier, refund, 75000)
    assert (result["full_refund_hours"], result["reschedule_hours"]) == (12, 6)


def test_early_cancellation_refunds_everything_paid(client, db, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18,))  # hủy trước 34 tiếng

    assert cancel(client, world.p1, booking).status_code == 400            # thiếu thông tin nhận tiền hoàn
    assert cancel(client, world.p1, booking, {"bank_account": "0123"}).status_code == 400
    response = cancel(client, world.p1, booking, {**BANK, "reason": "Bận việc"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "CANCELLED" and body["cancel_reason"] == "Bận việc" and body["cancelled_at"]
    assert (body["refund_status"], body["refund_amount"]) == ("PENDING", 75000)
    assert (body["refund_bank_account"], body["refund_bank_name"], body["refund_account_holder"]) == (
        "0123456789", "Vietcombank", "NGUYEN VAN A")
    assert all(not d["is_active"] for d in body["details"])

    # Khung giờ được trả lại ngay cho người khác
    assert client.post(BOOKINGS, json={"details": [slot(world.court, day, 18)]}, headers=auth(world.p2)).status_code == 200
    assert cancel(client, world.p1, booking, BANK).status_code == 400      # không hủy hai lần


def test_late_cancellation_forfeits_the_deposit_but_returns_any_excess(client, world, clock):
    day = clock.day(1)
    deposit_only = confirmed_booking(client, world.p1, world.court, day, hours=(18,))
    paid_in_full = create_booking(client, world.p2, world.venue_a.courts[1], day, hours=(18,))
    sepay(client, paid_in_full["booking_code"], paid_in_full["total_price"])  # chuyển luôn 100%

    clock.set(day, 13, 0)  # còn 5 tiếng
    first = cancel(client, world.p1, deposit_only)                          # không có gì để hoàn nên không cần tài khoản
    assert first.status_code == 200
    assert first.json()["refund_status"] is None and first.json()["refund_amount"] == 0

    second_preview = preview(client, world.p2, paid_in_full)
    assert (second_preview["tier"], second_preview["refund_amount"]) == ("NO_REFUND", 75000)
    second = cancel(client, world.p2, paid_in_full, BANK)
    assert (second.json()["refund_status"], second.json()["refund_amount"]) == ("PENDING", 75000)


def test_unpaid_booking_can_be_cancelled_without_bank_details(client, world, clock):
    day = clock.day(1)
    booking = create_booking(client, world.p1, world.court, day, hours=(18,))
    assert preview(client, world.p1, booking)["tier"] == "UNPAID"

    response = client.delete(f"{BOOKINGS}/{booking['id']}", headers=auth(world.p1))  # đường dẫn cũ vẫn dùng được
    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED" and response.json()["refund_status"] is None
    assert client.post(BOOKINGS, json={"details": [slot(world.court, day, 18)]}, headers=auth(world.p2)).status_code == 200


def test_cancelling_a_partially_paid_pending_booking_requests_a_refund(client, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    sepay(client, booking["booking_code"], 30000)

    assert preview(client, world.p1, booking)["refund_amount"] == 30000
    assert cancel(client, world.p1, booking).status_code == 400
    assert cancel(client, world.p1, booking, BANK).json()["refund_amount"] == 30000


def test_expired_booking_with_partial_payment_gets_a_refund_request(client, db, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    sepay(client, booking["booking_code"], 30000)
    clock.advance(minutes=16)
    booking_service.expire_stale_pending(db)

    stored = db.get(Booking, booking["id"])
    assert (stored.status, stored.refund_status, stored.refund_amount) == ("EXPIRED", "PENDING", 30000)


def test_player_cannot_cancel_after_checkin_or_someone_elses_booking(client, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(9,))
    assert cancel(client, world.p2, booking, BANK).status_code == 404
    assert client.get(f"{BOOKINGS}/{booking['id']}/cancel-preview", headers=auth(world.p2)).status_code == 404

    clock.set(day, 8, 55)
    client.post(f"{BOOKINGS}/{booking['id']}/checkin", headers=auth(world.staff_a))
    assert preview(client, world.p1, booking)["can_cancel"] is False
    assert cancel(client, world.p1, booking, BANK).status_code == 400


# ---------------------------------------------------------------------------
# Cụm sân hủy và xác nhận hoàn tiền
# ---------------------------------------------------------------------------
def test_venue_cancellation_always_refunds_in_full(client, world, clock):
    day = clock.day(1)
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(18,))
    clock.set(day, 16, 0)  # sát giờ: nếu người chơi tự hủy thì mất cọc

    response = client.put(f"{BOOKINGS}/{booking['id']}/status", json={"status": "CANCELLED", "reason": "Sân ngập nước"},
                          headers=auth(world.staff_a))
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["refund_status"], body["refund_amount"]) == ("CANCELLED", "PENDING", 75000)
    assert body["cancel_reason"] == "Sân ngập nước"


def test_confirming_a_refund_writes_it_to_the_ledger_once(client, db, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    cancel(client, world.p1, booking, BANK)
    path = f"{BOOKINGS}/{booking['id']}/confirm-refund"

    assert client.post(path, headers=auth(world.p1)).status_code == 403
    response = client.post(path, json={"note": "Đã chuyển khoản hoàn cọc"}, headers=auth(world.owner_a))
    assert response.status_code == 200, response.text
    assert response.json()["refund_status"] == "COMPLETED" and response.json()["refunded_at"]

    refund = db.query(PaymentTransaction).filter_by(booking_id=booking["id"], kind="REFUND").one()
    assert (refund.amount_in, refund.created_by_id, refund.transaction_content) == (
        75000, world.owner_a.id, "Đã chuyển khoản hoàn cọc")
    assert client.post(path, headers=auth(world.owner_a)).status_code == 400
    assert db.query(PaymentTransaction).filter_by(kind="REFUND").count() == 1


def test_refund_cannot_be_confirmed_when_none_is_pending(client, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    response = client.post(f"{BOOKINGS}/{booking['id']}/confirm-refund", headers=auth(world.owner_a))
    assert response.status_code == 400
