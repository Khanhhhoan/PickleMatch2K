"""
Quên mật khẩu (người chơi): xin liên kết qua email, đặt mật khẩu mới bằng liên kết đó.

Thư được ghi ra thư mục outbox (EMAIL_BACKEND=file trong kiểm thử), không gửi thật. Liên kết hạn 30 phút theo đồng hồ
nghiệp vụ, dùng một lần; mật khẩu đổi là mọi liên kết và phiên đăng nhập cũ hết hiệu lực.
"""
import re

import httpx
import pytest

from app.core.config import settings
from app.services import email_service
from helpers import auth, make_user, make_venue

FORGOT = "/api/v1/auth/forgot-password"
RESET = "/api/v1/auth/reset-password"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/users/me"
GENERIC = ("Nếu email này thuộc một tài khoản người chơi, chúng tôi đã gửi hướng dẫn đặt lại mật khẩu. "
           "Vui lòng kiểm tra hộp thư, kể cả mục Spam.")
INVALID = "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn. Hãy yêu cầu liên kết mới."
DONE = "Đã đặt lại mật khẩu. Hãy đăng nhập bằng mật khẩu mới."
EMAIL = "an.nguyen@mailbox.vn"
NEW_PASSWORD = "matkhau-moi-1"
LINK = re.compile(r"http://localhost:3000/reset-password\?token=([A-Za-z0-9_.\-]+)")


@pytest.fixture
def player(db):
    return make_user(db, "PLAYER", EMAIL, full_name="Nguyễn An")


def ask(client, email: str = EMAIL):
    return client.post(FORGOT, json={"email": email})


def link_token(mail: dict) -> str:
    match = LINK.search(mail["text"])
    assert match, mail["text"]
    assert match.group(0) in mail["html"]
    return match.group(1)


def reset(client, token: str, password: str = NEW_PASSWORD):
    return client.post(RESET, json={"token": token, "new_password": password})


def login(client, email: str = EMAIL, password: str = "secret123"):
    return client.post(LOGIN, data={"username": email, "password": password})


def test_player_gets_one_mail_and_the_link_resets_the_password(client, player, outbox):
    response = ask(client)

    assert response.status_code == 200
    assert response.json() == {"message": GENERIC}
    mails = outbox()
    assert [mail["to"] for mail in mails] == [EMAIL]
    assert mails[0]["subject"] == "Đặt lại mật khẩu PickleMatch2K"
    assert "Nguyễn An" in mails[0]["text"] and "30 phút" in mails[0]["text"]

    done = reset(client, link_token(mails[0]))

    assert done.status_code == 200, done.text
    assert done.json() == {"message": DONE}
    assert login(client, password=NEW_PASSWORD).status_code == 200
    assert login(client).status_code == 401


def test_same_answer_and_no_mail_for_unknown_blocked_staff_and_locked(client, db, player, outbox):
    owner = make_user(db, "OWNER", "chu.san@mailbox.vn")
    make_user(db, "STAFF", "nhan.vien@mailbox.vn", venue=make_venue(db, owner))
    make_user(db, "PLAYER", "player01@gmail.com")  # tài khoản mẫu do hệ thống tạo: không bao giờ nhận thư
    locked = make_user(db, "PLAYER", "bi.khoa@mailbox.vn")
    locked.is_active = False
    db.commit()

    emails = ("khong.co@mailbox.vn", "player01@gmail.com", "chu.san@mailbox.vn", "nhan.vien@mailbox.vn",
              "bi.khoa@mailbox.vn", EMAIL)
    answers = [ask(client, email) for email in emails]

    assert {(answer.status_code, answer.text) for answer in answers} == {(200, answers[-1].text)}
    assert [mail["to"] for mail in outbox()] == [EMAIL]  # chỉ người chơi hợp lệ nhận thư


def test_email_is_matched_ignoring_case_and_spaces(client, player, outbox):
    assert ask(client, "  An.Nguyen@MAILBOX.vn ").status_code == 200

    assert [mail["to"] for mail in outbox()] == [EMAIL]


def test_a_link_works_once_and_takes_the_other_link_with_it(client, player, outbox, clock):
    ask(client)
    clock.advance(minutes=1)
    ask(client)
    first, second = (link_token(mail) for mail in outbox())
    assert first != second

    assert reset(client, first).status_code == 200

    again = reset(client, first, "matkhau-khac-2")
    assert again.status_code == 400
    assert again.json()["detail"] == INVALID
    assert reset(client, second, "matkhau-khac-2").status_code == 400


def test_link_expires_after_30_minutes(client, player, outbox, clock):
    ask(client)
    token = link_token(outbox()[0])

    clock.advance(minutes=31)

    assert reset(client, token).status_code == 400


def test_link_dies_when_the_password_is_changed_another_way(client, player, outbox):
    ask(client)
    token = link_token(outbox()[0])
    changed = client.post("/api/v1/users/me/change-password", headers=auth(player),
                          json={"current_password": "secret123", "new_password": "doi-cach-khac-1"})
    assert changed.status_code == 200

    assert reset(client, token).status_code == 400


def test_reset_and_login_tokens_are_not_interchangeable(client, player, outbox):
    ask(client)
    reset_token = link_token(outbox()[0])

    assert client.get(ME, headers={"Authorization": f"Bearer {reset_token}"}).status_code == 401
    login_token = login(client).json()["access_token"]
    assert reset(client, login_token).status_code == 400
    assert reset(client, "chuoi-rac-khong-phai-ma").status_code == 400


def test_reset_signs_out_other_sessions(client, player, outbox):
    session = {"Authorization": f"Bearer {login(client).json()['access_token']}"}
    ask(client)

    assert reset(client, link_token(outbox()[0])).status_code == 200

    assert client.get(ME, headers=session).status_code == 401


def test_link_rejected_after_the_account_is_locked(client, db, player, outbox):
    ask(client)
    token = link_token(outbox()[0])
    player.is_active = False
    db.commit()

    assert reset(client, token).status_code == 400


def test_reset_clears_the_login_lockout(client, player, outbox):
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert login(client, password="sai-mat-khau").status_code == 401
    assert login(client, password="sai-mat-khau").status_code == 429

    ask(client)
    assert reset(client, link_token(outbox()[0])).status_code == 200

    assert login(client, password=NEW_PASSWORD).status_code == 200


def test_rate_limit_per_email(client, player, outbox):
    for _ in range(3):
        assert ask(client).status_code == 200

    blocked = ask(client)

    assert blocked.status_code == 429
    assert "quá nhiều lần" in blocked.json()["detail"]
    assert len(outbox()) == 3


def test_rate_limit_per_ip(client, outbox):
    for n in range(10):
        assert ask(client, f"khach{n}@mailbox.vn").status_code == 200

    assert ask(client, "khach10@mailbox.vn").status_code == 429


def test_new_password_rules(client, player, outbox):
    ask(client)

    assert reset(client, link_token(outbox()[0]), "12345").status_code == 422


def test_unconfigured_mail_gives_503(client, player, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", None)

    response = ask(client)

    assert response.status_code == 503
    assert response.json()["detail"] == "Chức năng quên mật khẩu đang tạm ngưng. Vui lòng liên hệ quản trị viên."


def test_production_needs_an_https_web_address(client, player, monkeypatch):
    """Bản chạy thật thiếu WEB_APP_URL thì liên kết trong thư sẽ trỏ về localhost: báo tạm ngưng thay vì gửi."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "khoa-brevo-gia")
    monkeypatch.setattr(settings, "EMAIL_FROM", "gui-thu@pickle2k.vn")
    monkeypatch.setattr(email_service.httpx, "post", lambda url, **kwargs: type("R", (), {"status_code": 201, "text": ""})())

    monkeypatch.setattr(settings, "WEB_APP_URL", "http://localhost:3000")
    assert ask(client).status_code == 503

    monkeypatch.setattr(settings, "WEB_APP_URL", "https://picklematch2k-web.onrender.com")
    assert ask(client).status_code == 200


def test_mail_provider_failure_still_gives_the_generic_answer(client, player, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "khoa-brevo-gia")
    monkeypatch.setattr(settings, "EMAIL_FROM", "gui-thu@pickle2k.vn")
    tried = []

    def broken(url, **kwargs):
        tried.append(kwargs["json"]["to"])
        raise httpx.ConnectTimeout("hết thời gian chờ")

    monkeypatch.setattr(email_service.httpx, "post", broken)

    response = ask(client)

    assert response.status_code == 200
    assert response.json() == {"message": GENERIC}
    assert tried == [[{"email": EMAIL}]]  # đã thử gửi đúng người
