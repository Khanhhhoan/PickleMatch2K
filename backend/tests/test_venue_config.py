"""Cấu hình cụm sân: sân con, giờ hoạt động, bảng giá, ảnh, đánh giá, duyệt cụm sân và lịch trống."""
import io
from datetime import date, time

import pytest
from PIL import Image

from app.models.venue import Court, PriceRule, Venue
from app.services import storage_service
from app.services.availability_service import calculate_slot_price
from helpers import auth, confirmed_booking, create_booking, make_user, make_venue, slot

VENUES = "/api/v1/venues"
BOOKINGS = "/api/v1/bookings"
WEEKDAY, SATURDAY = date(2030, 1, 2), date(2030, 1, 5)   # thứ Tư và thứ Bảy


def rules(base=None, peak=None, weekend=None, peak_window=(time(17, 0), time(23, 0))):
    items = []
    if base:
        items.append(PriceRule(rule_type="BASE", price=base))
    if peak:
        items.append(PriceRule(rule_type="PEAK", price=peak, start_time=peak_window[0], end_time=peak_window[1]))
    if weekend:
        items.append(PriceRule(rule_type="WEEKEND", price=weekend))
    return items


def price(hour, day=WEEKDAY, court=None, **kwargs):
    return calculate_slot_price(time(hour, 0), time(hour + 1, 0), rules(**kwargs), target_date=day, court=court)


def availability(client, venue, day, user=None):
    response = client.get(f"/api/v1/search/venues/{venue.id}/availability", params={"target_date": day.isoformat()},
                          headers=auth(user) if user else {})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Tính giá một khung giờ
# ---------------------------------------------------------------------------
def test_slot_price_rules():
    assert price(9, base=100000, peak=150000) == 100000
    assert price(16, base=100000, peak=150000) == 100000
    assert price(17, base=100000, peak=150000) == 150000          # khung bắt đầu đúng giờ cao điểm
    assert price(22, base=100000, peak=150000) == 150000
    assert price(9, base=100000, peak=150000, peak_window=(time(6, 0), time(10, 0))) == 150000
    assert price(9, base=100000) == 100000 and price(18, base=100000) == 100000
    assert price(18, base=100000, peak=80000) == 100000           # giá cao điểm không thấp hơn giá thường
    assert price(9) == 160000                                     # chưa cấu hình giá: dùng mức mặc định


def test_weekend_and_court_specific_prices():
    assert price(9, SATURDAY, base=100000, peak=150000, weekend=130000) == 130000
    assert price(18, SATURDAY, base=100000, peak=150000, weekend=130000) == 150000   # lấy mức cao hơn
    assert price(18, SATURDAY, base=100000, peak=150000, weekend=180000) == 180000
    assert price(9, WEEKDAY, base=100000, weekend=130000) == 100000

    vip = Court(name="VIP", price=250000)
    assert price(9, court=vip, base=100000, peak=150000) == 250000
    assert price(18, court=vip, base=100000, peak=150000) == 250000
    assert price(9, court=Court(name="Thường", price=0), base=100000) == 100000


def test_booking_total_is_the_sum_of_each_hour_across_the_peak_boundary(client, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(15, 16, 17, 18))
    assert [d["price"] for d in booking["details"]] == [100000, 100000, 150000, 150000]
    assert booking["total_price"] == 500000 and booking["deposit_amount"] == 250000


# ---------------------------------------------------------------------------
# Lịch trống
# ---------------------------------------------------------------------------
def test_availability_grid_marks_past_booked_and_free_slots(client, world, clock):
    today = clock.today
    create_booking(client, world.p1, world.court, today, hours=(18,))
    grid = availability(client, world.venue_a, today)

    assert grid["venue_id"] == world.venue_a.id and len(grid["courts"]) == 2
    first = {s["start_time"]: s for s in grid["courts"][0]["slots"]}
    assert list(first)[0] == "05:00:00" and list(first)[-1] == "22:00:00" and len(first) == 18
    assert first["07:00:00"]["is_past"] and not first["07:00:00"]["is_available"]
    assert first["08:00:00"]["is_past"]                                    # đúng 08:00 thì khung 08:00 đã bắt đầu
    assert first["09:00:00"]["is_available"] and not first["09:00:00"]["is_past"]
    assert not first["18:00:00"]["is_available"] and not first["18:00:00"]["is_past"]
    assert (first["16:00:00"]["price"], first["17:00:00"]["price"]) == (100000, 150000)
    other_court = {s["start_time"]: s for s in grid["courts"][1]["slots"]}
    assert other_court["18:00:00"]["is_available"]


def test_availability_frees_slots_of_expired_and_cancelled_bookings(client, world, clock):
    day = clock.day(1)
    expiring = create_booking(client, world.p1, world.court, day, hours=(18,))
    cancelled = create_booking(client, world.p2, world.court, day, hours=(19,))
    client.post(f"{BOOKINGS}/{cancelled['id']}/cancel", headers=auth(world.p2))

    def free(hour):
        slots = availability(client, world.venue_a, day)["courts"][0]["slots"]
        return next(s for s in slots if s["start_time"] == f"{hour}:00:00")["is_available"]

    assert (free(18), free(19)) == (False, True)
    clock.advance(minutes=16)                       # đơn chờ cọc quá hạn: lịch hiển thị trống ngay
    assert free(18) is True
    assert expiring["status"] == "PENDING"


def test_availability_for_closed_days_far_dates_and_hidden_venues(client, db, world, clock):
    closed_day = clock.day(2)
    venue = make_venue(db, world.owner_a, closed_days=(closed_day.weekday(),), courts=1)
    assert availability(client, venue, closed_day)["courts"] == []

    far = availability(client, world.venue_a, clock.day(61))["courts"][0]["slots"]
    assert far and not any(s["is_available"] for s in far)

    world.venue_a.courts[1].status = "MAINTENANCE"
    world.venue_b.status = "MAINTENANCE"
    db.commit()
    assert len(availability(client, world.venue_a, clock.day(1))["courts"]) == 1
    assert availability(client, world.venue_b, clock.day(1))["courts"] == []
    assert client.get("/api/v1/search/venues/99999/availability", params={"target_date": clock.today.isoformat()}).status_code == 404
    assert client.get(f"/api/v1/search/venues/{venue.id}/availability").status_code == 422


def test_search_by_keyword_and_distance(client, db, world):
    make_venue(db, world.owner_a, name="Pickle 100% Arena", lat=None, lng=None)

    def names(**params):
        return [v["name"] for v in client.get("/api/v1/search/venues", params=params).json()]

    assert names(keyword="sân b") == ["Sân B"]
    assert names(keyword="100%") == ["Pickle 100% Arena"] and names(keyword="%") == ["Pickle 100% Arena"]
    assert names(keyword="_") == []                                     # ký tự đại diện của LIKE được coi là chữ thường
    assert names(latitude=10.85, longitude=106.75) == ["Sân B", "Sân A", "Pickle 100% Arena"]   # chưa có toạ độ xếp cuối
    assert names(latitude=10.85, longitude=106.75, radius_km=3) == ["Sân B"]
    nearest = client.get("/api/v1/search/venues", params={"latitude": 10.85, "longitude": 106.75}).json()[0]
    assert nearest["distance_km"] == 0


# ---------------------------------------------------------------------------
# Sân con, giờ hoạt động, bảng giá
# ---------------------------------------------------------------------------
def test_court_management(client, db, world, clock):
    owner, base = auth(world.owner_a), f"{VENUES}/{world.venue_a.id}/courts"
    created = client.post(base, json={"name": "Sân VIP", "price": 250000}, headers=owner).json()
    assert (created["name"], created["price"], created["status"]) == ("Sân VIP", 250000, "ACTIVE")
    assert client.post(base, json={"name": ""}, headers=owner).status_code == 422
    assert client.post(base, json={"name": "x", "status": "BROKEN"}, headers=owner).status_code == 422

    vip = db.get(Court, created["id"])
    assert create_booking(client, world.p1, vip, clock.day(1), hours=(9,))["total_price"] == 250000

    path = f"{base}/{created['id']}"
    paused = client.put(path, json={"status": "MAINTENANCE", "price": 0}, headers=owner).json()
    assert (paused["status"], paused["price"]) == ("MAINTENANCE", None)
    assert client.post(BOOKINGS, json={"details": [slot(vip, clock.day(1), 10)]}, headers=auth(world.p1)).status_code == 400

    assert client.delete(path, headers=owner).status_code == 409             # đã có lịch sử đặt
    spare = client.post(base, json={"name": "Sân thừa"}, headers=owner).json()
    assert client.delete(f"{base}/{spare['id']}", headers=owner).status_code == 200
    assert client.delete(f"{base}/{spare['id']}", headers=owner).status_code == 404


def test_operating_hours(client, world, clock):
    owner, path = auth(world.owner_a), f"{VENUES}/{world.venue_a.id}/operating-hours"
    day = clock.day(1)

    assert client.post(path, json={"day_of_week": 7, "open_time": "06:00", "close_time": "22:00"}, headers=owner).status_code == 422
    assert client.post(path, json={"day_of_week": 0, "open_time": "22:00", "close_time": "06:00"}, headers=owner).status_code == 422
    one = client.post(path, json={"day_of_week": day.weekday(), "open_time": "08:00", "close_time": "12:00"}, headers=owner)
    assert one.status_code == 200
    slots = availability(client, world.venue_a, day)["courts"][0]["slots"]
    assert [s["start_time"] for s in slots] == ["08:00:00", "09:00:00", "10:00:00", "11:00:00"]

    duplicate_days = {"hours": [{"day_of_week": 1, "open_time": "06:00", "close_time": "22:00"}] * 2}
    assert client.put(path, json=duplicate_days, headers=owner).status_code == 422
    only_one_day = {"hours": [{"day_of_week": day.weekday(), "open_time": "06:00", "close_time": "09:00"}]}
    replaced = client.put(path, json=only_one_day, headers=owner).json()
    assert len(replaced) == 1
    assert len(availability(client, world.venue_a, day)["courts"][0]["slots"]) == 3
    assert availability(client, world.venue_a, clock.day(2))["courts"] == []     # các ngày khác thành ngày nghỉ


def test_pricing_update_replaces_the_three_rules(client, db, world, clock):
    owner, path = auth(world.owner_a), f"{VENUES}/{world.venue_a.id}/pricing"
    assert client.put(path, json={"base_price": 0}, headers=owner).status_code == 422
    assert client.put(path, json={"base_price": 120000, "peak_start": "20:00", "peak_end": "18:00"}, headers=owner).status_code == 422

    result = client.put(path, json={"base_price": 120000, "peak_price": 180000, "weekend_price": 140000,
                                    "peak_start": "18:00", "peak_end": "22:00"}, headers=owner).json()
    assert (result["base_price"], result["peak_price"], result["weekend_price"]) == (120000, 180000, 140000)
    assert (result["peak_start"], result["peak_end"]) == ("18:00", "22:00")
    stored = {r.rule_type: r.price for r in db.query(PriceRule).filter_by(venue_id=world.venue_a.id)}
    assert stored == {"BASE": 120000, "PEAK": 180000, "WEEKEND": 140000}       # không sinh thêm dòng trùng

    client.post(path, json={"base_price": 110000}, headers=owner)               # bỏ trống thì bằng giá thường
    assert {r.rule_type: r.price for r in db.query(PriceRule).filter_by(venue_id=world.venue_a.id)} == {
        "BASE": 110000, "PEAK": 110000, "WEEKEND": 110000}
    assert client.post(f"{VENUES}/{world.venue_a.id}/price-rules", json={"rule_type": "HAPPY", "price": 1}, headers=owner).status_code == 400


def test_venue_details_update(client, db, world):
    wifi = make_amenity(db, "Wifi")
    response = client.put(f"{VENUES}/{world.venue_a.id}", headers=auth(world.owner_a), json={
        "name": " Sân A Mới ", "description": "Mô tả", "latitude": 10.8, "longitude": 106.7,
        "amenity_ids": [wifi.id, 9999], "bank_account": " 777888999 - TPBank ", "images": ["/uploads/venues/a.png"],
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["latitude"]) == ("Sân A Mới", 10.8)
    assert [a["name"] for a in body["amenities"]] == ["Wifi"]
    assert body["google_maps_url"].endswith("query=10.8,106.7")
    db.expire_all()
    assert world.owner_a.owner_profile.bank_account == "777888999 - TPBank"
    assert client.put(f"{VENUES}/{world.venue_a.id}", json={"latitude": 95}, headers=auth(world.owner_a)).status_code == 422
    assert [a["name"] for a in client.get(f"{VENUES}/amenities").json()] == ["Wifi"]


def make_amenity(db, name):
    from app.models.venue import Amenity

    amenity = Amenity(name=name)
    db.add(amenity)
    db.commit()
    return amenity


# ---------------------------------------------------------------------------
# Duyệt cụm sân
# ---------------------------------------------------------------------------
def test_owner_registered_venue_waits_for_admin_approval(client, db, world):
    newcomer = make_user(db, "OWNER")
    created = client.post(VENUES, headers=auth(newcomer), json={"name": "Sân Mới", "address": "5 Trần Phú", "status": "ACTIVE"})
    assert created.status_code == 200 and created.json()["status"] == "PENDING"     # không tự bật ACTIVE được
    venue_id = created.json()["id"]
    assert client.post(VENUES, headers=auth(newcomer), json={"name": "Sân Hai", "address": "6 Trần Phú"}).status_code == 400

    assert "Sân Mới" not in [v["name"] for v in client.get(VENUES).json()]
    assert [v["status"] for v in client.get(f"{VENUES}/me", headers=auth(newcomer)).json()] == ["PENDING"]
    status_path = f"{VENUES}/{venue_id}/status"
    assert client.put(status_path, json={"status": "ACTIVE"}, headers=auth(newcomer)).status_code == 403

    approved = client.put(f"{VENUES}/admin/{venue_id}", json={"status": "ACTIVE"}, headers=auth(world.admin))
    assert approved.json()["status"] == "ACTIVE"
    assert "Sân Mới" in [v["name"] for v in client.get(VENUES).json()]
    # Sau khi được duyệt, chủ sân tự tạm đóng/mở lại nhưng không tự đặt các trạng thái của Admin
    assert client.put(status_path, json={"status": "MAINTENANCE"}, headers=auth(newcomer)).json()["status"] == "MAINTENANCE"
    assert client.put(status_path, json={"status": "ACTIVE"}, headers=auth(newcomer)).json()["status"] == "ACTIVE"
    assert client.put(status_path, json={"status": "REJECTED"}, headers=auth(newcomer)).status_code == 403

    client.put(status_path, json={"status": "REJECTED"}, headers=auth(world.admin))
    assert client.put(status_path, json={"status": "ACTIVE"}, headers=auth(newcomer)).status_code == 403


def test_admin_venue_management(client, db, world, clock):
    admin = auth(world.admin)
    not_owner = {"name": "Sân X", "address": "1 A", "owner_id": world.p1.id}
    assert client.post(f"{VENUES}/admin", json=not_owner, headers=admin).status_code == 400
    created = client.post(f"{VENUES}/admin", headers=admin, json={
        "name": "Sân X", "address": "1 A", "owner_id": world.owner_b.id, "courts_count": 3, "base_price": 90000}).json()
    assert len(created["courts"]) == 3 and created["price_rules"][0]["price"] == 90000

    listing = client.get(f"{VENUES}/admin/all", headers=admin).json()
    assert len(listing) == 3 and listing[0]["owner_bank_account"] == "111222333 - MBBank"

    path = f"{VENUES}/admin/{created['id']}"
    assert client.put(f"{path}/assign-owner", json={"owner_id": world.p1.id}, headers=admin).status_code == 400
    assert client.put(f"{path}/assign-owner", json={"owner_id": world.owner_a.id}, headers=admin).json()["owner_id"] == world.owner_a.id
    assert client.delete(path, headers=admin).status_code == 200
    assert client.delete(path, headers=admin).status_code == 404

    create_booking(client, world.p1, world.court, clock.day(1), hours=(9,))
    assert client.delete(f"{VENUES}/admin/{world.venue_a.id}", headers=admin).status_code == 409   # đã có lịch sử đặt
    assert db.get(Venue, world.venue_a.id) is not None


# ---------------------------------------------------------------------------
# Ảnh
# ---------------------------------------------------------------------------
def image_bytes(fmt="PNG"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_service, "VENUE_UPLOAD_DIR", str(tmp_path))
    return tmp_path


def upload(client, user, venue, content, filename="photo.png", content_type="image/png", primary="true"):
    return client.post(f"{VENUES}/{venue.id}/upload-image", headers=auth(user),
                       files={"file": (filename, content, content_type)}, data={"is_primary": primary})


def test_image_upload_detects_the_real_format_and_stores_locally(client, world, upload_dir):
    disguised = upload(client, world.owner_a, world.venue_a, image_bytes("JPEG"), filename="evil.svg", content_type="image/svg+xml")
    assert disguised.status_code == 200, disguised.text
    url = disguised.json()["uploaded_file"]
    assert url.startswith("/uploads/venues/venue_") and url.endswith(".jpg")      # đuôi file theo nội dung thật
    assert (upload_dir / url.rsplit("/", 1)[1]).exists()
    assert disguised.json()["image_url"] == url

    gallery = upload(client, world.owner_a, world.venue_a, image_bytes("PNG"), primary="false").json()
    assert gallery["image_url"] == url and len(gallery["images"]) == 2            # ảnh thư viện không thay ảnh bìa


@pytest.mark.parametrize("content, name, mime", [
    (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "x.svg", "image/svg+xml"),
    (b"<html><script>alert(1)</script></html>", "x.png", "image/png"),
    (b"MZ\x90\x00 not an image", "x.jpg", "image/jpeg"),
    (b"", "empty.png", "image/png"),
])
def test_non_images_are_rejected_whatever_they_claim_to_be(client, world, upload_dir, content, name, mime):
    assert upload(client, world.owner_a, world.venue_a, content, filename=name, content_type=mime).status_code == 400
    assert list(upload_dir.iterdir()) == []


def test_oversized_upload_is_rejected(client, world, upload_dir, monkeypatch):
    monkeypatch.setattr(storage_service.settings, "MAX_IMAGE_SIZE_MB", 0)
    assert upload(client, world.owner_a, world.venue_a, image_bytes()).status_code == 400


def test_image_deletion_is_limited_to_the_venues_own_images(client, world, upload_dir):
    url = upload(client, world.owner_a, world.venue_a, image_bytes()).json()["uploaded_file"]
    stored = upload_dir / url.rsplit("/", 1)[1]
    outside = upload_dir.parent / "secret.txt"
    outside.write_text("keep me")

    path = f"{VENUES}/{world.venue_a.id}/images"
    assert client.delete(f"{VENUES}/{world.venue_b.id}/images", params={"image_url": url}, headers=auth(world.owner_b)).status_code == 404
    assert client.delete(path, params={"image_url": "/uploads/venues/../secret.txt"}, headers=auth(world.owner_a)).status_code == 404
    assert stored.exists() and outside.exists()

    removed = client.delete(path, params={"image_url": url}, headers=auth(world.owner_a)).json()
    assert removed["images"] == [] and removed["image_url"] is None and not stored.exists()
    assert storage_service.delete_venue_image_file("/uploads/venues/../secret.txt") is False and outside.exists()


# ---------------------------------------------------------------------------
# Đánh giá
# ---------------------------------------------------------------------------
def test_only_players_who_completed_a_booking_can_review_once(client, db, world, clock):
    day = clock.day(1)
    path = f"{VENUES}/{world.venue_a.id}/reviews"
    booking = confirmed_booking(client, world.p1, world.court, day, hours=(9,))
    review = {"rating": 5, "comment": "  Sân đẹp  "}

    assert client.post(path, json=review, headers=auth(world.p1)).status_code == 403      # mới cọc, chưa chơi
    assert client.post(path, json=review, headers=auth(world.p2)).status_code == 403
    clock.set(day, 8, 55)
    client.post(f"{BOOKINGS}/{booking['id']}/checkin", headers=auth(world.staff_a))
    client.put(f"{BOOKINGS}/{booking['id']}/status", json={"status": "COMPLETED"}, headers=auth(world.staff_a))

    first = client.post(path, json=review, headers=auth(world.p1))
    assert first.status_code == 200
    assert (first.json()["comment"], first.json()["author_name"]) == ("Sân đẹp", world.p1.player_profile.full_name)
    again = client.post(path, json={"rating": 3}, headers=auth(world.p1)).json()          # gửi lại là sửa đánh giá cũ
    assert again["id"] == first.json()["id"] and (again["rating"], again["comment"]) == (3, None)

    listed = client.get(path).json()
    assert len(listed) == 1 and "@" not in str(listed)
    for bad in ({"rating": 0}, {"rating": 6}, {"rating": 4, "comment": "x" * 1001}):
        assert client.post(path, json=bad, headers=auth(world.p1)).status_code == 422
    assert client.post(f"{VENUES}/{world.venue_b.id}/reviews", json=review, headers=auth(world.p1)).status_code == 403
    assert client.post(f"{VENUES}/99999/reviews", json=review, headers=auth(world.p1)).status_code == 404
