"""Doanh thu theo tháng và theo năm: các khoản trong sổ giao dịch gom theo giờ Việt Nam.

Chủ sân và admin xem được; nhân viên chỉ xem doanh thu hôm nay nên bị từ chối. Cộng các ngày ra đúng số của tháng,
cộng các tháng ra đúng số của năm.
"""
from datetime import date

from helpers import auth, confirmed_booking, create_booking, sepay

BOOKINGS = "/api/v1/bookings"
MONTHLY = f"{BOOKINGS}/revenue/monthly"
YEARLY = f"{BOOKINGS}/revenue/yearly"
REFUND_TO = {"bank_account": "0123456789", "bank_name": "Vietcombank", "account_holder": "NGUYEN VAN A"}


def get(client, url, user, **params):
    response = client.get(url, params=params, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def desk_cash(client, staff, court, day, start, end):
    response = client.post(f"{BOOKINGS}/desk", headers=auth(staff), json={
        "court_id": court.id, "date": day.isoformat(), "start_time": start, "end_time": end, "payment_method": "CASH"})
    assert response.status_code == 200, response.text
    return response.json()


def money(bucket):
    return bucket["collected"], bucket["refunded"], bucket["net"]


def test_month_and_year_follow_vietnam_time_split_by_method_with_refunds(client, world, clock):
    play_day = date(2025, 4, 5)

    clock.set(date(2025, 3, 10), 9, 0)
    confirmed_booking(client, world.p1, world.court, play_day, hours=(9,))                    # cọc 50k chuyển khoản
    desk_cash(client, world.staff_a, world.court, date(2025, 3, 10), "18:00:00", "19:00:00")  # 150k tiền mặt, chơi 10/3
    confirmed_booking(client, world.p3, world.venue_b.courts[0], play_day, hours=(9,))       # cụm sân khác: 100k
    clock.set(date(2025, 3, 31), 23, 50)                                                     # 23:50 ngày cuối tháng 3
    cancelled = confirmed_booking(client, world.p2, world.venue_a.courts[1], play_day, hours=(9,))  # cọc 50k, hủy sau
    clock.set(date(2025, 4, 1), 0, 10)                                                       # 00:10 đã sang tháng 4
    assert client.post(f"{BOOKINGS}/{cancelled['id']}/cancel", json=REFUND_TO, headers=auth(world.p2)).status_code == 200
    assert client.post(f"{BOOKINGS}/{cancelled['id']}/confirm-refund", json={"bank_reference": "FT26MONTH0001"},
                       headers=auth(world.owner_a)).status_code == 200                       # hoàn 50k
    late = create_booking(client, world.p3, world.court, play_day, hours=(10,))
    sepay(client, late["booking_code"], late["deposit_amount"])                              # cọc 50k chuyển khoản
    clock.set(date(2025, 4, 20), 9, 0)

    march = get(client, MONTHLY, world.owner_a, month="2025-03")
    assert (march["month"], march["venue_names"]) == ("2025-03", ["Sân A"])
    assert (march["collected"], march["cash"], march["transfer"], march["refunded"], march["net"]) == (
        250000, 150000, 100000, 0, 250000)
    assert (march["plays_total"], march["plays_arrived"]) == (1, 0)                   # chỉ lượt chơi ngày 10/3
    assert (len(march["days"]), march["days"][0]["date"], march["days"][-1]["date"]) == (31, "2025-03-01", "2025-03-31")
    active = {d["date"]: money(d) for d in march["days"] if d["collected"] or d["refunded"]}
    assert active == {"2025-03-10": (200000, 0, 200000), "2025-03-31": (50000, 0, 50000)}

    april = get(client, MONTHLY, world.owner_a, month="2025-04")
    assert (april["collected"], april["cash"], april["transfer"], april["refunded"], april["net"]) == (
        50000, 0, 50000, 50000, 0)
    assert (april["plays_total"], len(april["days"])) == (2, 30)                       # đơn đã hủy không tính lượt chơi
    assert money(april["days"][0]) == (50000, 50000, 0)
    assert sum(d["net"] for d in april["days"]) == april["net"]

    year = get(client, YEARLY, world.owner_a, year=2025)
    assert (year["year"], year["collected"], year["cash"], year["transfer"], year["refunded"], year["net"]) == (
        2025, 300000, 150000, 150000, 50000, 250000)
    assert (year["plays_total"], year["plays_arrived"]) == (3, 0)
    assert [m["month"] for m in year["months"]] == [f"2025-{m:02d}" for m in range(1, 13)]
    assert [money(m) for m in year["months"][2:4]] == [(250000, 0, 250000), (50000, 50000, 0)]
    assert sum(m["net"] for m in year["months"]) == year["net"]

    other = get(client, MONTHLY, world.owner_b, month="2025-03")
    assert (other["venue_names"], other["collected"]) == (["Sân B"], 100000)
    everything = get(client, YEARLY, world.admin, year=2025)
    assert (everything["venue_names"], everything["collected"], everything["net"]) == (["Sân A", "Sân B"], 400000, 350000)


def test_staff_players_future_and_malformed_periods_are_refused(client, world, clock):
    clock.set(date(2025, 4, 20), 9, 0)
    for url, params in ((MONTHLY, {"month": "2025-04"}), (YEARLY, {"year": 2025})):
        refused = client.get(url, params=params, headers=auth(world.staff_a))
        assert refused.status_code == 403 and "hôm nay" in refused.json()["detail"]
        assert client.get(url, params=params, headers=auth(world.p1)).status_code == 403

    current = get(client, MONTHLY, world.owner_a)                                     # mặc định là tháng hiện tại
    assert (current["month"], current["net"], len(current["days"])) == ("2025-04", 0, 30)
    assert get(client, YEARLY, world.owner_a)["year"] == 2025

    owner = auth(world.owner_a)
    for url, params in ((MONTHLY, {"month": "2025-05"}), (YEARLY, {"year": 2026})):
        future = client.get(url, params=params, headers=owner)
        assert future.status_code == 400 and "chưa tới" in future.json()["detail"]
    for bad in ("2025-13", "04-2025", "2025-4"):
        assert client.get(MONTHLY, params={"month": bad}, headers=owner).status_code == 422
    assert client.get(YEARLY, params={"year": "abc"}, headers=owner).status_code == 422
