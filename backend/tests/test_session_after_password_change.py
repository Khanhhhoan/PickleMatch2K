"""
Đổi mật khẩu thì các phiên đăng nhập cũ hết hiệu lực: token cấp lúc đăng nhập mang dấu vân tay của mật khẩu, mật khẩu
đổi là dấu vân tay đổi. Thiết bị vừa đổi mật khẩu nhận token mới nên vẫn ở trạng thái đăng nhập.
"""
from app.core.security import create_access_token
from helpers import make_user

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/users/me"
CHANGE = "/api/v1/users/me/change-password"
NEW_PASSWORD = "moi-123456"


def login(client, email: str, password: str = "secret123") -> dict:
    response = client.post(LOGIN, data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def change_password(client, headers: dict):
    return client.post(CHANGE, headers=headers, json={"current_password": "secret123", "new_password": NEW_PASSWORD})


def test_login_token_dies_when_password_changes(client, db):
    player = make_user(db, "PLAYER", "an.nguyen@mailbox.vn")
    phone, laptop = login(client, player.email), login(client, player.email)

    assert change_password(client, laptop).status_code == 200

    assert client.get(ME, headers=phone).status_code == 401


def test_change_password_returns_a_working_token(client, db):
    player = make_user(db, "PLAYER", "binh.tran@mailbox.vn")
    before = login(client, player.email)

    response = change_password(client, before)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    fresh = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get(ME, headers=fresh).status_code == 200
    assert client.get(ME, headers=before).status_code == 401
    assert client.post(LOGIN, data={"username": player.email, "password": NEW_PASSWORD}).status_code == 200


def test_tokens_without_fingerprint_still_work(client, db):
    """Token cấp trước bản này (không có dấu vân tay) vẫn dùng được tới khi hết hạn, kể cả khi mật khẩu đã đổi."""
    player = make_user(db, "PLAYER", "chi.le@mailbox.vn")
    legacy = {"Authorization": f"Bearer {create_access_token(player.id)}"}

    assert change_password(client, legacy).status_code == 200

    assert client.get(ME, headers=legacy).status_code == 200
