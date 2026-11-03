"""Ảnh đại diện của người chơi: xử lý ảnh khi tải lên, thay và xóa ảnh, quyền, và hiển thị trong phòng đấu."""
import io

import pytest
from PIL import Image

from app.services import storage_service
from helpers import auth, confirmed_booking

ME = "/api/v1/users/me"
MATCHES = "/api/v1/matches"


def photo(fmt="JPEG", size=(1200, 800), color="orange", gps=False) -> bytes:
    """Ảnh thử; gps=True gắn EXIF có toạ độ nơi chụp như ảnh chụp bằng điện thoại."""
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"                                  # Make
        exif.get_ifd(0x8825)[2] = (10.0, 46.0, 30.0)                  # GPSLatitude
        image.save(buffer, format=fmt, exif=exif)
    else:
        image.save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def avatar_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_service, "AVATAR_UPLOAD_DIR", str(tmp_path))
    return tmp_path


def upload(client, user, content, name="me.jpg", mime="image/jpeg"):
    return client.post(f"{ME}/avatar", headers=auth(user), files={"file": (name, content, mime)})


def stored_file(avatar_dir, url):
    return avatar_dir / url.rsplit("/", 1)[1]


def test_upload_makes_a_small_square_webp_without_metadata(client, world, avatar_dir):
    original = photo(gps=True)
    with Image.open(io.BytesIO(original)) as img:
        assert img.getexif()                                         # ảnh gốc có EXIF (máy chụp, GPS)

    response = upload(client, world.p1, original)
    assert response.status_code == 200, response.text
    url = response.json()["player_profile"]["avatar_url"]
    assert url.startswith("/uploads/avatars/user_") and url.endswith(".webp")
    with Image.open(stored_file(avatar_dir, url)) as img:
        assert img.format == "WEBP" and img.size == (320, 320)       # cắt vuông, thu nhỏ
        assert not img.getexif()                                     # không còn siêu dữ liệu nào
    assert stored_file(avatar_dir, url).stat().st_size < len(original)
    assert client.get(ME, headers=auth(world.p1)).json()["player_profile"]["avatar_url"] == url


def test_transparent_png_keeps_its_transparency(client, world, avatar_dir):
    image = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    url = upload(client, world.p1, buffer.getvalue(), name="logo.png", mime="image/png").json()["player_profile"]["avatar_url"]
    with Image.open(stored_file(avatar_dir, url)) as img:
        assert img.mode == "RGBA" and img.getpixel((10, 10))[3] == 0


def test_a_new_avatar_replaces_and_deletes_the_old_file(client, world, avatar_dir):
    first = upload(client, world.p1, photo(color="red")).json()["player_profile"]["avatar_url"]
    second = upload(client, world.p1, photo(fmt="PNG", color="blue"), name="me.png", mime="image/png")
    assert second.status_code == 200
    new_url = second.json()["player_profile"]["avatar_url"]
    assert new_url != first and stored_file(avatar_dir, new_url).exists()
    assert not stored_file(avatar_dir, first).exists()               # ảnh cũ không để lại rác


def test_removing_the_avatar(client, world, avatar_dir):
    url = upload(client, world.p1, photo()).json()["player_profile"]["avatar_url"]
    response = client.delete(f"{ME}/avatar", headers=auth(world.p1))
    assert response.status_code == 200 and response.json()["player_profile"]["avatar_url"] is None
    assert not stored_file(avatar_dir, url).exists()
    assert client.delete(f"{ME}/avatar", headers=auth(world.p1)).status_code == 200   # chưa có ảnh: vẫn được


@pytest.mark.parametrize("content, name, mime", [
    (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "x.svg", "image/svg+xml"),
    (b"<html><script>alert(1)</script></html>", "x.jpg", "image/jpeg"),
    (b"MZ\x90\x00 not an image", "x.png", "image/png"),
    (b"", "empty.jpg", "image/jpeg"),
])
def test_non_images_are_rejected_whatever_they_claim_to_be(client, world, avatar_dir, content, name, mime):
    assert upload(client, world.p1, content, name=name, mime=mime).status_code == 400
    assert list(avatar_dir.iterdir()) == []
    assert client.get(ME, headers=auth(world.p1)).json()["player_profile"]["avatar_url"] is None


def test_oversized_files_and_huge_images_are_rejected(client, world, avatar_dir, monkeypatch):
    monkeypatch.setattr(storage_service, "AVATAR_MAX_PIXELS", 100 * 100)
    assert upload(client, world.p1, photo(size=(200, 200))).status_code == 400       # quá nhiều điểm ảnh
    monkeypatch.setattr(storage_service.settings, "MAX_IMAGE_SIZE_MB", 0)
    assert upload(client, world.p1, photo(size=(50, 50))).status_code == 400         # quá dung lượng
    assert list(avatar_dir.iterdir()) == []


def test_only_players_have_an_avatar(client, world, avatar_dir):
    for user in (world.owner_a, world.staff_a, world.admin):
        assert upload(client, user, photo()).status_code == 403
        assert client.delete(f"{ME}/avatar", headers=auth(user)).status_code == 403
    assert client.post(f"{ME}/avatar", files={"file": ("me.jpg", photo(), "image/jpeg")}).status_code == 401


def test_the_avatar_address_cannot_be_set_through_the_profile_form(client, world, avatar_dir):
    response = client.put(f"{ME}/profile", headers=auth(world.p1),
                          json={"full_name": "Người Chơi Một", "avatar_url": "https://tracker.example/pixel.png"})
    assert response.status_code == 200
    assert response.json()["player_profile"]["avatar_url"] is None
    assert response.json()["player_profile"]["full_name"] == "Người Chơi Một"


def test_room_cards_show_the_avatars_of_the_host_and_members(client, world, avatar_dir, clock):
    host, member = world.players[0], world.players[1]
    host_url = upload(client, host, photo(color="green")).json()["player_profile"]["avatar_url"]
    booking = confirmed_booking(client, host, world.court, clock.day(2), hours=(18,))
    room = client.post(MATCHES, json={"booking_id": booking["id"]}, headers=auth(host)).json()
    assert client.post(f"{MATCHES}/{room['id']}/join", headers=auth(member)).status_code == 200
    assert client.post(f"{MATCHES}/{room['id']}/requests/{member.id}/accept", headers=auth(host)).status_code == 200

    seen = next(m for m in client.get(MATCHES, headers=auth(member)).json() if m["id"] == room["id"])
    assert seen["creator_avatar_url"] == host_url
    by_user = {p["user_id"]: p for p in seen["participants"]}
    assert by_user[host.id]["avatar_url"] == host_url and by_user[member.id]["avatar_url"] is None
