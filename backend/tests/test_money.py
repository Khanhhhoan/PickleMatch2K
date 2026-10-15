"""Tiền VNĐ là số nguyên đồng ở mọi tầng: cột BIGINT, phép tính bằng int, API trả và nhận số nguyên."""
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.booking_policy import deposit_for
from app.core.money import split_evenly, vnd
from helpers import auth, confirmed_booking, create_booking

BOOKINGS = "/api/v1/bookings"
VENUES = "/api/v1/venues"

MONEY_COLUMNS = {
    ("bookings", "total_price"), ("bookings", "deposit_amount"), ("bookings", "paid_amount"), ("bookings", "refund_amount"),
    ("booking_details", "price"), ("payment_transactions", "amount_in"),
    ("shift_closings", "opening_float"), ("shift_closings", "counted_cash"), ("shift_closings", "cash_collected"),
    ("shift_closings", "transfer_collected"), ("shift_closings", "refunded"),
    ("courts", "price"), ("price_rules", "price"),
}


def is_whole(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Phép tính
# ---------------------------------------------------------------------------
def test_amounts_are_whole_dong_and_rounding_matches_the_previous_rule():
    assert vnd(None) == 0 and vnd(150000) == 150000 and vnd(Decimal("200000")) == 200000 and vnd("75000") == 75000
    # Làm tròn về số chẵn gần nhất, đúng như round() của bản trước: tiền cọc của một tổng lẻ không đổi
    assert (vnd(125000.5), vnd(125001.5), vnd(Decimal("99999.49"))) == (125000, 125002, 99999)
    assert deposit_for(250001) == 125000 and deposit_for(150000) == 75000 and is_whole(deposit_for(100001))
    for bad in (float("nan"), float("inf"), "nhiều"):
        with pytest.raises(ValueError):
            vnd(bad)
    with pytest.raises(TypeError):
        vnd(True)


@pytest.mark.parametrize("total, parts", [(250001, 3), (100000, 3), (7, 4), (1_000_000_007, 12)])
def test_splitting_a_total_across_slots_always_adds_up_exactly(total, parts):
    pieces = split_evenly(total, parts)
    assert len(pieces) == parts and sum(pieces) == total and all(is_whole(p) for p in pieces)
    assert max(pieces) - min(pieces) <= parts


# ---------------------------------------------------------------------------
# Cơ sở dữ liệu
# ---------------------------------------------------------------------------
def test_every_money_column_is_a_bigint(db):
    rows = db.execute(text(
        "SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema = 'public'"
    )).all()
    types = {(table, column): data_type for table, column, data_type in rows}
    assert {column: types[column] for column in MONEY_COLUMNS} == {column: "bigint" for column in MONEY_COLUMNS}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
def test_the_api_returns_money_as_whole_numbers(client, world, clock):
    booking = confirmed_booking(client, world.p1, world.court, clock.day(1), hours=(18, 19))
    for field in ("total_price", "deposit_amount", "paid_amount", "remaining_amount", "refund_amount"):
        assert is_whole(booking[field]), (field, booking[field])
    assert all(is_whole(d["price"]) for d in booking["details"])

    stats = client.get(f"{BOOKINGS}/owner/stats", headers=auth(world.owner_a)).json()
    assert all(is_whole(stats[key]) for key in ("total_revenue", "collected_amount", "refunded_amount", "deposit_collected"))
    assert all(is_whole(day["revenue"]) for day in stats["daily"])

    transactions = client.get("/api/v1/payments/transactions", headers=auth(world.owner_a)).json()
    assert transactions and all(is_whole(t["amount_in"]) for t in transactions)
    shift = client.get("/api/v1/payments/shift-closings", headers=auth(world.staff_a)).json()
    assert all(is_whole(shift[key]) for key in ("cash_collected", "transfer_collected", "refunded", "total_collected"))


def test_fractional_money_is_refused_instead_of_rounded(client, world, clock):
    unpaid = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    owner = auth(world.owner_a)
    assert client.post(f"{BOOKINGS}/{unpaid['id']}/collect", json={"amount": 50000.5}, headers=owner).status_code == 422
    courts = f"{VENUES}/{world.venue_a.id}/courts"
    assert client.post(courts, json={"name": "Sân lẻ", "price": 150000.5}, headers=owner).status_code == 422
    pricing = {"base_price": 100000.5, "peak_price": 150000, "weekend_price": 160000}
    assert client.put(f"{VENUES}/{world.venue_a.id}/pricing", json=pricing, headers=owner).status_code == 422
    # Số nguyên gửi kèm phần thập phân 0 (ví dụ 50000.0 từ JavaScript) vẫn được nhận
    collected = client.post(f"{BOOKINGS}/{unpaid['id']}/collect", json={"amount": 75000.0}, headers=owner)
    assert collected.status_code == 200, collected.text
    assert collected.json()["paid_amount"] == 75000 and is_whole(collected.json()["paid_amount"])
