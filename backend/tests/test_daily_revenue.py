"""Doanh thu theo ngày: các khoản của đúng một ngày (giờ Việt Nam) trong sổ giao dịch.

Chủ sân và admin xem được mọi ngày đã qua; nhân viên chỉ xem hôm nay của cụm sân mình trực.
"""
from helpers import auth, confirmed_booking, create_booking, sepay

BOOKINGS = "/api/v1/bookings"
DAILY = f"{BOOKINGS}/revenue/daily"
REFUND_TO = {"bank_account": "0123456789", "bank_name": "Vietcombank", "account_holder": "NGUYEN VAN A"}


def daily(client, user, day=None):
    response = client.get(DAILY, params={"date": day.isoformat()} if day else {}, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def desk_cash(client, staff, court, day, start, end, path="desk"):
    response = client.post(f"{BOOKINGS}/{path}", headers=auth(staff), json={
        "court_id": court.id, "date": day.isoformat(), "start_time": start, "end_time": end, "payment_method": "CASH"})
    assert response.status_code == 200, response.text
    return response.json()


def test_owner_sees_one_past_day_split_by_method_with_refunds(client, world, clock):
    today, yesterday, play_day = clock.today, clock.day(-1), clock.day(3)

    clock.set(yesterday, 10, 0)
    online = confirmed_booking(client, world.p1, world.court, play_day, hours=(9,))                # cọc 50k chuyển khoản
    cancelled = confirmed_booking(client, world.p2, world.venue_a.courts[1], play_day, hours=(9,))  # cọc 50k, hủy sau
    desk = desk_cash(client, world.staff_a, world.court, yesterday, "18:00:00", "19:00:00")         # 150k tiền mặt
    clock.set(yesterday, 12, 0)
    confirmed_booking(client, world.p3, world.venue_b.courts[0], play_day, hours=(9,))             # cụm sân khác: 100k
    clock.set(yesterday, 23, 50)                                                                    # hoàn 50k cuối ngày
    assert client.post(f"{BOOKINGS}/{cancelled['id']}/cancel", json=REFUND_TO, headers=auth(world.p2)).status_code == 200
    assert client.post(f"{BOOKINGS}/{cancelled['id']}/confirm-refund", json={"bank_reference": "FT26DAILY0001"},
                       headers=auth(world.owner_a)).status_code == 200
    clock.set(today, 0, 10)                                                                         # đã sang hôm nay
    late = create_booking(client, world.p3, world.court, play_day, hours=(10,))
    sepay(client, late["booking_code"], late["deposit_amount"])

    day = daily(client, world.owner_a, yesterday)
    assert (day["date"], day["venue_names"]) == (yesterday.isoformat(), ["Sân A"])
    assert (day["collected"], day["cash"], day["transfer"], day["refunded"], day["net"]) == (
        250000, 150000, 100000, 50000, 200000)
    assert (day["plays_total"], day["plays_arrived"]) == (1, 0)                    # chỉ lượt chơi rơi vào hôm qua
    # Danh sách đúng các khoản đã cộng, mới trước cũ sau
    assert [(t["kind"], t["method"], t["amount_in"], t["booking"]["booking_code"]) for t in day["transactions"]] == [
        ("REFUND", "BANK_TRANSFER", 50000, cancelled["booking_code"]),
        ("DEPOSIT", "CASH", 150000, desk["booking_code"]),
        ("DEPOSIT", "BANK_TRANSFER", 50000, cancelled["booking_code"]),
        ("DEPOSIT", "BANK_TRANSFER", 50000, online["booking_code"]),
    ]

    # Hôm nay chỉ có khoản cọc lúc 00:10; không truyền ngày thì là hôm nay
    assert (daily(client, world.owner_a, today)["collected"], daily(client, world.owner_a)["collected"]) == (50000, 50000)
    assert daily(client, world.owner_a)["date"] == today.isoformat()

    other = daily(client, world.owner_b, yesterday)
    assert (other["venue_names"], other["collected"], len(other["transactions"])) == (["Sân B"], 100000, 1)
    everything = daily(client, world.admin, yesterday)
    assert (everything["venue_names"], everything["collected"], everything["net"]) == (["Sân A", "Sân B"], 350000, 300000)


def test_staff_see_today_at_their_venue_only(client, world, clock):
    today = clock.today
    desk_cash(client, world.staff_a, world.court, today, "09:00:00", "10:00:00", path="staff/walkin")  # 100k, đã vào sân
    online = create_booking(client, world.p1, world.court, today, hours=(18,))
    sepay(client, online["booking_code"], online["deposit_amount"])                                   # 75k, chờ đến

    day = daily(client, world.staff_a)
    assert (day["date"], day["venue_names"]) == (today.isoformat(), ["Sân A"])
    assert (day["collected"], day["cash"], day["transfer"], day["refunded"], day["net"]) == (175000, 100000, 75000, 0, 175000)
    assert (day["plays_total"], day["plays_arrived"], len(day["transactions"])) == (2, 1, 2)
    assert daily(client, world.staff_a, today)["collected"] == 175000          # chọn đúng hôm nay vẫn được
    assert daily(client, world.staff_b)["collected"] == 0                      # nhân viên cụm sân khác không thấy

    refused = client.get(DAILY, params={"date": clock.day(-1).isoformat()}, headers=auth(world.staff_a))
    assert refused.status_code == 403 and "hôm nay" in refused.json()["detail"]


def test_future_and_malformed_dates_are_refused(client, world, clock):
    owner = auth(world.owner_a)
    future = client.get(DAILY, params={"date": clock.day(1).isoformat()}, headers=owner)
    assert future.status_code == 400 and "chưa tới" in future.json()["detail"]
    assert client.get(DAILY, params={"date": "25-10-2026"}, headers=owner).status_code == 422
    assert client.get(DAILY, headers=auth(world.p1)).status_code == 403
