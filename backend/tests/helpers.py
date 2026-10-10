"""Hàm dựng dữ liệu và thao tác API dùng chung cho các file test (fixture nằm ở conftest.py)."""
from datetime import date, datetime, time, timedelta
from typing import Dict, Optional

WEBHOOK_KEY = "test-webhook-key"
TEST_BANK_ACCOUNT = "9990001112223"

_counter = {"n": 0}


def auth(user) -> Dict[str, str]:
    """Header đăng nhập của một người dùng (cấp token trực tiếp, không qua /auth/login)."""
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


# ---------------------------------------------------------------------------
# Dựng dữ liệu
# ---------------------------------------------------------------------------
def make_user(db, role: str = "PLAYER", email: Optional[str] = None, *, password: str = "secret123",
              full_name: Optional[str] = None, phone: Optional[str] = None, venue=None, **profile):
    from app.services.user_service import create_user

    _counter["n"] += 1
    email = email or f"{role.lower()}{_counter['n']}@example.com"
    user = create_user(db, email=email, password=password, role=role, full_name=full_name or f"{role.title()} {_counter['n']}",
                       phone=phone, venue_id=venue.id if venue is not None else None)
    target = user.player_profile or user.owner_profile
    for field, value in profile.items():
        setattr(target, field, value)
    db.commit()
    db.refresh(user)
    return user


def make_venue(db, owner, *, name: Optional[str] = None, courts: int = 2, open_time: time = time(5, 0),
               close_time: time = time(23, 0), base: float = 100000, peak: Optional[float] = 150000,
               weekend: Optional[float] = None, lat: Optional[float] = 10.78, lng: Optional[float] = 106.70,
               status: str = "ACTIVE", closed_days: tuple = (), amenities: tuple = ()):
    from app.models.venue import Court, OperatingHour, PriceRule, Venue

    _counter["n"] += 1
    venue = Venue(owner_id=owner.id, name=name or f"Cụm sân {_counter['n']}", address="1 Đường Thử Nghiệm, TP. Hồ Chí Minh",
                  latitude=lat, longitude=lng, status=status)
    venue.amenities = list(amenities)
    db.add(venue)
    db.flush()
    for index in range(1, courts + 1):
        db.add(Court(venue_id=venue.id, name=f"Sân {index}", status="ACTIVE"))
    for day_of_week in range(7):
        if day_of_week not in closed_days:
            db.add(OperatingHour(venue_id=venue.id, day_of_week=day_of_week, open_time=open_time, close_time=close_time))
    db.add(PriceRule(venue_id=venue.id, rule_type="BASE", price=base))
    if peak:
        db.add(PriceRule(venue_id=venue.id, rule_type="PEAK", start_time=time(17, 0), end_time=time(23, 0), price=peak))
    if weekend:
        db.add(PriceRule(venue_id=venue.id, rule_type="WEEKEND", price=weekend))
    db.commit()
    db.refresh(venue)
    return venue


# ---------------------------------------------------------------------------
# Thao tác qua API
# ---------------------------------------------------------------------------
def slot(court, day: date, hour: int, minute: int = 0) -> dict:
    start = datetime.combine(day, time(hour, minute))
    return {
        "court_id": court.id,
        "date": day.isoformat(),
        "start_time": start.time().isoformat(),
        "end_time": (start + timedelta(hours=1)).time().isoformat(),
    }


def create_booking(client, user, court, day: date, hours=(18,), expect: int = 200) -> dict:
    """Người chơi đặt các khung giờ (theo giờ bắt đầu) trên một sân."""
    response = client.post("/api/v1/bookings", json={"details": [slot(court, day, h) for h in hours]}, headers=auth(user))
    assert response.status_code == expect, response.text
    return response.json()


def sepay(client, content: str, amount: float, *, reference: Optional[str] = None, account: Optional[str] = TEST_BANK_ACCOUNT,
          transfer_type: str = "in", key: Optional[str] = WEBHOOK_KEY, expect: int = 200) -> dict:
    """Gọi webhook SePay như ngân hàng báo có một giao dịch."""
    _counter["n"] += 1
    payload = {
        "gateway": "MBBank",
        "accountNumber": account,
        "transferType": transfer_type,
        "transferAmount": amount,
        "content": content,
        "referenceCode": reference or f"FT{_counter['n']:08d}",
    }
    headers = {"Authorization": f"Apikey {key}"} if key else {}
    response = client.post("/api/v1/payments/sepay-webhook", json=payload, headers=headers)
    assert response.status_code == expect, response.text
    return response.json()


def pay_deposit(client, booking: dict) -> dict:
    result = sepay(client, f"{booking['booking_code']} chuyen khoan coc", booking["deposit_amount"])
    assert result.get("outcome") == "confirmed", result
    return result


def confirmed_booking(client, user, court, day: date, hours=(18,)) -> dict:
    """Đơn đã thanh toán đủ cọc (trạng thái CONFIRMED)."""
    booking = create_booking(client, user, court, day, hours)
    pay_deposit(client, booking)
    return get_booking(client, user, booking["id"])


def get_booking(client, user, booking_id: int) -> dict:
    response = client.get("/api/v1/bookings/me", headers=auth(user))
    assert response.status_code == 200, response.text
    return next(b for b in response.json() if b["id"] == booking_id)
