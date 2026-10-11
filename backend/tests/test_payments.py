"""Thông tin thanh toán, webhook SePay (xác thực, khớp đơn, chống ghi trùng, tiền đến muộn) và sổ giao dịch."""
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.models.booking import Booking
from app.models.payment import PaymentTransaction
from app.services import booking_service
from app.services.payment_service import parse_owner_bank_info
from helpers import TEST_BANK_ACCOUNT, WEBHOOK_KEY, auth, confirmed_booking, create_booking, get_booking, sepay, slot

PAYMENTS = "/api/v1/payments"
BOOKINGS = "/api/v1/bookings"


@pytest.fixture
def pending(client, world, clock):
    """Đơn 1 khung giờ cao điểm: tổng 150.000đ, cọc 75.000đ."""
    return create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))


def transactions(db, booking):
    return db.query(PaymentTransaction).filter_by(booking_id=booking["id"]).order_by(PaymentTransaction.id).all()


# ---------------------------------------------------------------------------
# Thông tin thanh toán
# ---------------------------------------------------------------------------
def test_checkout_shows_deposit_account_and_qr(client, world, pending):
    response = client.get(f"{PAYMENTS}/checkout/{pending['id']}", headers=auth(world.p1))
    assert response.status_code == 200, response.text
    body = response.json()

    assert (body["total_price"], body["deposit_amount"], body["amount_due"], body["remaining_amount"]) == (
        150000, 75000, 75000, 75000)
    assert (body["bank_account_number"], body["bank_code"], body["transfer_content"]) == (
        TEST_BANK_ACCOUNT, "MB", "PK2K000001")
    assert body["expires_in_seconds"] == 900 and body["simulator_enabled"] is True
    query = parse_qs(urlparse(body["qr_code_url"]).query)
    assert query == {"acc": [TEST_BANK_ACCOUNT], "bank": ["MB"], "amount": ["75000"], "des": ["PK2K000001"]}


def test_checkout_amount_due_shrinks_after_a_partial_transfer(client, world, pending):
    sepay(client, pending["booking_code"], 30000)
    body = client.get(f"{PAYMENTS}/checkout/{pending['id']}", headers=auth(world.p1)).json()
    assert (body["paid_amount"], body["amount_due"], body["payment_status"]) == (30000, 45000, "PARTIALLY_PAID")


def test_checkout_is_visible_only_to_the_customer_and_the_venue(client, world, pending):
    path = f"{PAYMENTS}/checkout/{pending['id']}"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth(world.p2)).status_code == 404
    assert client.get(path, headers=auth(world.staff_b)).status_code == 403
    assert client.get(path, headers=auth(world.owner_b)).status_code == 403
    for allowed in (world.staff_a, world.owner_a, world.admin):
        assert client.get(path, headers=auth(allowed)).status_code == 200


def test_missing_receiving_account_is_reported_instead_of_using_a_hidden_default(client, world, pending, monkeypatch):
    monkeypatch.setattr(settings, "SEPAY_BANK_ACCOUNT", "")
    assert client.get(f"{PAYMENTS}/checkout/{pending['id']}", headers=auth(world.p1)).status_code == 503


def test_per_owner_account_mode(client, db, world, pending, monkeypatch):
    monkeypatch.setattr(settings, "SEPAY_UNIFIED_TEST_MODE", False)
    body = client.get(f"{PAYMENTS}/checkout/{pending['id']}", headers=auth(world.p1)).json()
    assert (body["bank_account_number"], body["bank_code"], body["account_holder_name"]) == ("111222333", "MB", "CHU SAN A")

    # Tiền chuyển vào tài khoản khác với tài khoản của chủ sân thì không được ghi nhận cho đơn
    assert sepay(client, pending["booking_code"], 75000)["status"] == "ignored"
    assert sepay(client, pending["booking_code"], 75000, account="111222333")["outcome"] == "confirmed"

    world.owner_a.owner_profile.bank_account = None
    db.commit()
    assert client.get(f"{PAYMENTS}/checkout/{pending['id']}", headers=auth(world.p1)).status_code == 409


@pytest.mark.parametrize("raw, expected", [
    ("0765883535 - Techcombank (Van Anh)", ("0765883535", "Techcombank", "TCB")),
    ("0901234567 (MBBank)", ("0901234567", "MBBank", "MB")),
    ("vietcombank 1023456789", ("1023456789", "Vietcombank", "VCB")),
    ("Chưa có tài khoản", None),
    ("123456789", None),
    ("", None),
    (None, None),
])
def test_parse_owner_bank_info(raw, expected):
    assert parse_owner_bank_info(raw) == expected


# ---------------------------------------------------------------------------
# Xác thực webhook
# ---------------------------------------------------------------------------
def test_webhook_requires_the_configured_key(client, db, pending):
    assert sepay(client, pending["booking_code"], 75000, key=None, expect=401)
    assert sepay(client, pending["booking_code"], 75000, key="wrong-key", expect=401)
    assert sepay(client, pending["booking_code"], 75000, key=WEBHOOK_KEY[:-1], expect=401)
    assert transactions(db, pending) == []

    body = {"transferType": "in", "transferAmount": 75000, "content": pending["booking_code"], "referenceCode": "B1"}
    bearer = client.post(f"{PAYMENTS}/sepay-webhook", json=body, headers={"Authorization": f"Bearer {WEBHOOK_KEY}"})
    assert bearer.status_code == 200 and bearer.json()["outcome"] == "confirmed"


def test_webhook_without_a_key_is_refused_in_production_but_allowed_in_development(client, pending, monkeypatch):
    monkeypatch.setattr(settings, "SEPAY_WEBHOOK_API_KEY", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    sepay(client, pending["booking_code"], 75000, key=None, expect=503)

    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert sepay(client, pending["booking_code"], 75000, key=None)["outcome"] == "confirmed"


def test_webhook_acknowledges_every_delivery_the_way_sepay_expects(client, db, pending):
    """
    SePay chỉ coi một lần gọi là thành công khi nhận HTTP 200/201 kèm body có "success": true; thiếu trường này
    SePay tính là thất bại và gọi lại tới 7 lần, kể cả khi giao dịch đã được ghi nhận.
    """
    unrelated = sepay(client, "chuyen tien an trua", 50000)                      # tiền vào không liên quan đơn nào
    outgoing = sepay(client, "rut tien", 30000, transfer_type="out")
    partial = sepay(client, pending["booking_code"], 20000)
    confirmed = sepay(client, pending["booking_code"], 55000, reference="FT-ACK")
    repeated = sepay(client, pending["booking_code"], 55000, reference="FT-ACK")  # SePay gửi lại cùng giao dịch

    assert [r["success"] for r in (unrelated, outgoing, partial, confirmed, repeated)] == [True] * 5
    assert (unrelated["status"], outgoing["status"], partial["outcome"], confirmed["outcome"]) == (
        "ignored", "ignored", "partial", "confirmed")
    assert len(transactions(db, pending)) == 2

    # Yêu cầu sai khóa không được xác nhận là đã nhận
    refused = sepay(client, pending["booking_code"], 75000, key="wrong-key", expect=401)
    assert "success" not in refused


# ---------------------------------------------------------------------------
# Khớp đơn và cập nhật trạng thái
# ---------------------------------------------------------------------------
def test_exact_deposit_confirms_the_booking(client, db, world, pending):
    result = sepay(client, f"{pending['booking_code']} chuyen khoan coc", 75000, reference="FT001")
    assert (result["status"], result["outcome"], result["booking_status"], result["payment_status"]) == (
        "success", "confirmed", "CONFIRMED", "DEPOSIT_PAID")

    booking = get_booking(client, world.p1, pending["id"])
    assert (booking["status"], booking["paid_amount"], booking["remaining_amount"], booking["expires_at"]) == (
        "CONFIRMED", 75000, 75000, None)
    [txn] = transactions(db, pending)
    assert (txn.kind, txn.method, txn.amount_in, txn.reference_number, txn.transaction_code) == (
        "DEPOSIT", "BANK_TRANSFER", 75000, "FT001", "TX000001")


@pytest.mark.parametrize("content", [
    "PK2K000001", "pk2k000001", "PK2K 000001", "PK2K-000001 abc", "Thanh toan PK2K000001 cam on",
    "MBVCB.123456.PK2K000001.CT tu 0123", "PK2K1", "PKL 1",
])
def test_booking_code_is_found_in_free_form_transfer_content(client, pending, content):
    assert sepay(client, content, 75000)["outcome"] == "confirmed"


@pytest.mark.parametrize("overrides, reason", [
    ({"transfer_type": "out"}, "tiền vào"),
    ({"amount": 0}, "Số tiền"),
    ({"content": "chuyen tien an trua"}, "mã đặt sân"),
    ({"content": "PK2K000999"}, "mã đặt sân"),
    ({"account": "000111222"}, "Tài khoản nhận"),
])
def test_irrelevant_transactions_are_ignored_without_touching_the_booking(client, db, world, pending, overrides, reason):
    args = {"content": pending["booking_code"], "amount": 75000, **overrides}
    result = sepay(client, args.pop("content"), args.pop("amount"), **args)
    assert result["status"] == "ignored" and reason in result["reason"]
    assert transactions(db, pending) == []
    assert get_booking(client, world.p1, pending["id"])["status"] == "PENDING"


def test_partial_transfers_accumulate_until_the_deposit_is_met(client, db, world, pending):
    first = sepay(client, pending["booking_code"], 30000)
    assert (first["status"], first["outcome"], first["booking_status"], first["payment_status"]) == (
        "warning", "partial", "PENDING", "PARTIALLY_PAID")
    second = sepay(client, pending["booking_code"], 45000)
    assert (second["outcome"], second["booking_status"], second["payment_status"]) == ("confirmed", "CONFIRMED", "DEPOSIT_PAID")
    assert [t.amount_in for t in transactions(db, pending)] == [30000, 45000]

    third = sepay(client, pending["booking_code"], 75000)  # khách chuyển nốt phần còn lại trước khi đến sân
    assert (third["outcome"], third["payment_status"]) == ("updated", "FULLY_PAID")
    assert get_booking(client, world.p1, pending["id"])["remaining_amount"] == 0


def test_paying_the_full_price_up_front(client, world, pending):
    result = sepay(client, pending["booking_code"], 150000)
    assert (result["outcome"], result["booking_status"], result["payment_status"]) == ("confirmed", "CONFIRMED", "FULLY_PAID")


def test_rounding_difference_of_under_one_dong_still_confirms(client, pending):
    assert sepay(client, pending["booking_code"], 74999.5)["outcome"] == "confirmed"


def test_duplicate_webhook_delivery_is_recorded_once(client, db, world, pending):
    first = sepay(client, pending["booking_code"], 75000, reference="FT-DUP")
    again = sepay(client, pending["booking_code"], 75000, reference="FT-DUP")
    assert first["outcome"] == "confirmed" and again["status"] == "success" and "outcome" not in again
    assert len(transactions(db, pending)) == 1
    assert get_booking(client, world.p1, pending["id"])["paid_amount"] == 75000


# ---------------------------------------------------------------------------
# Tiền đến muộn
# ---------------------------------------------------------------------------
def test_late_payment_revives_an_expired_booking_when_the_slot_is_still_free(client, db, world, pending, clock):
    clock.advance(minutes=20)
    booking_service.expire_stale_pending(db)

    result = sepay(client, pending["booking_code"], 75000)
    assert (result["outcome"], result["booking_status"]) == ("reactivated", "CONFIRMED")
    db.expire_all()
    stored = db.get(Booking, pending["id"])
    assert all(d.is_active for d in stored.details) and stored.refund_status is None
    # Khung giờ lại thuộc về đơn này
    retry = client.post(BOOKINGS, json={"details": [slot(world.court, clock.day(1), 18)]}, headers=auth(world.p2))
    assert retry.status_code == 409


def test_late_payment_is_queued_for_refund_when_someone_else_took_the_slot(client, db, world, pending, clock):
    clock.advance(minutes=20)
    winner = confirmed_booking(client, world.p2, world.court, clock.day(1), hours=(18,))

    result = sepay(client, pending["booking_code"], 75000)
    assert (result["status"], result["outcome"], result["booking_status"]) == ("warning", "late_refund", "EXPIRED")
    db.expire_all()
    late = db.get(Booking, pending["id"])
    assert (late.refund_status, late.refund_amount, late.paid_amount) == ("PENDING", 75000, 75000)
    assert all(not d.is_active for d in late.details)
    assert get_booking(client, world.p2, winner["id"])["status"] == "CONFIRMED"


def test_late_payment_after_the_playing_time_is_refunded(client, db, pending, clock):
    clock.set(clock.day(1), 18, 30)
    booking_service.expire_stale_pending(db)
    assert sepay(client, pending["booking_code"], 75000)["outcome"] == "late_refund"


def test_payment_arriving_after_cancellation_is_queued_for_refund(client, db, world, pending):
    client.post(f"{BOOKINGS}/{pending['id']}/cancel", headers=auth(world.p1))
    result = sepay(client, pending["booking_code"], 75000)
    assert (result["outcome"], result["booking_status"]) == ("late_refund", "CANCELLED")
    stored = db.get(Booking, pending["id"])
    assert (stored.refund_status, stored.refund_amount) == ("PENDING", 75000)


# ---------------------------------------------------------------------------
# Giả lập thanh toán (chỉ khi bật cấu hình)
# ---------------------------------------------------------------------------
def test_simulator_confirms_the_deposit_when_enabled(client, db, world, pending):
    assert client.get(f"{PAYMENTS}/config").json() == {"simulator_enabled": True, "unified_account_mode": True}
    path = f"{PAYMENTS}/simulate-sepay/{pending['id']}"
    assert client.post(path, headers=auth(world.p2)).status_code == 404
    result = client.post(path, headers=auth(world.p1))
    assert result.status_code == 200 and result.json()["outcome"] == "confirmed"
    assert client.post(path, headers=auth(world.p1)).status_code == 400  # đơn không còn chờ cọc
    assert len(transactions(db, pending)) == 1


def test_simulator_is_not_reachable_when_disabled(client, world, pending, monkeypatch):
    monkeypatch.setattr(settings, "SEPAY_SIMULATOR_ENABLED", False)
    assert client.get(f"{PAYMENTS}/config").json()["simulator_enabled"] is False
    assert client.post(f"{PAYMENTS}/simulate-sepay/{pending['id']}", headers=auth(world.p1)).status_code == 404
    checkout = client.get(f"{PAYMENTS}/checkout/{pending['id']}", headers=auth(world.p1)).json()
    assert checkout["simulator_enabled"] is False


# ---------------------------------------------------------------------------
# Sổ giao dịch
# ---------------------------------------------------------------------------
def test_transaction_list_is_scoped_by_role(client, world, clock):
    confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    confirmed_booking(client, world.p2, world.venue_b.courts[0], clock.day(1), hours=(18,))

    def codes(user, query=""):
        response = client.get(f"{PAYMENTS}/transactions{query}", headers=auth(user))
        assert response.status_code == 200, response.text
        return sorted(t["booking"]["booking_code"] for t in response.json())

    assert codes(world.p1) == ["PK2K000001"] and codes(world.p2) == ["PK2K000002"] and codes(world.p3) == []
    assert codes(world.owner_a) == codes(world.staff_a) == ["PK2K000001"]
    assert codes(world.owner_b) == ["PK2K000002"]
    assert codes(world.admin) == ["PK2K000001", "PK2K000002"]
    assert codes(world.admin, f"?owner_id={world.owner_b.id}") == ["PK2K000002"]
    # Tham số owner_id của người không phải admin bị bỏ qua
    assert codes(world.owner_a, f"?owner_id={world.owner_b.id}") == ["PK2K000001"]
    assert client.get(f"{PAYMENTS}/transactions").status_code == 401
