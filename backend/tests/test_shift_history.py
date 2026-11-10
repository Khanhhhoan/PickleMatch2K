"""Lịch sử kết ca của chủ sân: mọi lần kết ca của một cụm sân trong một tháng (xếp theo ngày kết ca, giờ Việt Nam)
và các khoản thuộc từng lần kết ca, để lần ra khoản gây chênh lệch.

Nhân viên chỉ xem các lần kết ca gần đây trong hộp Kết ca (như doanh thu: chỉ hôm nay) nên bị từ chối.
"""
from datetime import date

from helpers import auth, create_booking, make_venue, sepay

BOOKINGS = "/api/v1/bookings"
SHIFTS = "/api/v1/payments/shift-closings"
HISTORY = f"{SHIFTS}/history"


def close(client, user, **body):
    response = client.post(SHIFTS, json={"opening_float": 0, "counted_cash": 0, **body}, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def get(client, url, user, **params):
    response = client.get(url, params=params, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def desk(client, user, court, day, start, end, payment_method="CASH"):
    body = {"court_id": court.id, "date": day.isoformat(), "start_time": start, "end_time": end, "payment_method": payment_method}
    response = client.post(f"{BOOKINGS}/desk", json=body, headers=auth(user))
    assert response.status_code == 200, response.text
    return response.json()


def test_history_lists_every_closing_of_a_month_by_its_vietnam_closing_date(client, db, world, clock):
    march = []
    for day in range(2, 14):                                       # 12 lần: nhiều hơn số lần hộp Kết ca trả về
        clock.set(date(2025, 3, day), 21, 0)
        march.append(close(client, world.staff_a))
    clock.set(date(2025, 3, 31), 23, 50)                           # 23:50 ngày cuối tháng 3
    march.append(close(client, world.staff_a, note="Ca tối cuối tháng"))
    clock.set(date(2025, 4, 1), 0, 10)                             # 00:10 đã sang tháng 4
    april = [close(client, world.owner_a)]
    clock.set(date(2025, 4, 20), 9, 0)

    history = get(client, HISTORY, world.owner_a, month="2025-03")
    assert (history["venue_id"], history["venue_name"], history["month"]) == (world.venue_a.id, "Sân A", "2025-03")
    assert history["first_date"] == "2025-03-02"
    assert history["closings"] == march[::-1]                      # đủ 13 lần, mới nhất trước, đúng số đã lưu
    assert get(client, HISTORY, world.owner_a, month="2025-04")["closings"] == april
    assert get(client, HISTORY, world.owner_a)["month"] == "2025-04"   # mặc định là tháng hiện tại
    assert get(client, HISTORY, world.owner_a, month="2025-02")["closings"] == []
    assert len(get(client, SHIFTS, world.owner_a)["closings"]) == 10   # hộp Kết ca vẫn chỉ trả các lần gần đây

    # Admin xem được mọi cụm sân; chủ sân khác chỉ thấy cụm sân của mình
    assert len(get(client, HISTORY, world.admin, venue_id=world.venue_a.id, month="2025-03")["closings"]) == 13
    other = get(client, HISTORY, world.owner_b, month="2025-03")
    assert (other["venue_name"], other["closings"], other["first_date"]) == ("Sân B", [], None)

    # Chủ sân có nhiều cụm sân chọn cụm sân cần xem; mặc định là cụm sân đầu tiên
    second = make_venue(db, world.owner_a, name="Sân A2")
    clock.set(date(2025, 4, 20), 10, 0)
    elsewhere = close(client, world.owner_a, venue_id=second.id)
    assert get(client, HISTORY, world.owner_a, venue_id=second.id)["closings"] == [elsewhere]
    assert get(client, HISTORY, world.owner_a)["closings"] == april


def test_each_closing_shows_exactly_the_transactions_it_took(client, world, clock):
    day = date(2025, 3, 10)
    court_1, court_2 = world.venue_a.courts
    clock.set(day, 8, 0)
    walk_in = desk(client, world.staff_a, court_1, day, "09:00:00", "10:00:00")                      # 100k tiền mặt
    online = create_booking(client, world.p1, court_2, day, hours=(18,))
    sepay(client, online["booking_code"], online["deposit_amount"])                                  # cọc 75k chuyển khoản
    clock.set(day, 12, 0)
    morning = close(client, world.staff_a, opening_float=200000, counted_cash=250000, note="Thiếu tiền lẻ")

    clock.set(day, 13, 0)
    transfer = desk(client, world.staff_a, court_1, day, "14:00:00", "15:00:00", payment_method="BANK_TRANSFER")  # 100k
    cash = desk(client, world.owner_a, court_1, day, "15:00:00", "16:00:00")                          # 100k tiền mặt
    clock.set(day, 22, 0)
    evening = close(client, world.owner_a, opening_float=200000, counted_cash=300000)

    def lines(closing):
        detail = get(client, f"{SHIFTS}/{closing['id']}", world.owner_a)
        assert {k: v for k, v in detail.items() if k != "transactions"} == closing                 # cùng số đã lưu
        return [(t["booking"]["booking_code"], t["method"], t["amount_in"]) for t in detail["transactions"]]

    assert lines(morning) == [(walk_in["booking_code"], "CASH", 100000), (online["booking_code"], "BANK_TRANSFER", 75000)]
    assert lines(evening) == [(transfer["booking_code"], "BANK_TRANSFER", 100000), (cash["booking_code"], "CASH", 100000)]
    assert (morning["difference"], evening["difference"]) == (-50000, 0)


def test_history_and_details_are_for_the_owner_of_the_venue_and_admin_only(client, world, clock):
    clock.set(date(2025, 4, 20), 9, 0)
    closing = close(client, world.staff_a)
    detail = f"{SHIFTS}/{closing['id']}"

    for url in (HISTORY, detail):
        refused = client.get(url, headers=auth(world.staff_a))
        assert refused.status_code == 403 and "gần đây" in refused.json()["detail"]
        assert client.get(url, headers=auth(world.p1)).status_code == 403
    assert client.get(HISTORY, params={"venue_id": world.venue_a.id}, headers=auth(world.owner_b)).status_code == 403
    assert client.get(detail, headers=auth(world.owner_b)).status_code == 403
    assert get(client, detail, world.admin)["id"] == get(client, detail, world.owner_a)["id"] == closing["id"]
    assert client.get(f"{SHIFTS}/999999", headers=auth(world.owner_a)).status_code == 404

    owner = auth(world.owner_a)
    future = client.get(HISTORY, params={"month": "2025-05"}, headers=owner)
    assert future.status_code == 400 and "chưa tới" in future.json()["detail"]
    for bad in ("2025-13", "04-2025", "2025-4"):
        assert client.get(HISTORY, params={"month": bad}, headers=owner).status_code == 422
