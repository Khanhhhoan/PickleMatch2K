"""Mật khẩu, token, đăng ký/đăng nhập, giới hạn đăng nhập sai và tài khoản bị khóa."""
from datetime import timedelta

import pytest
from jose import jwt
from pydantic import ValidationError

from app.core import rate_limit, security
from app.core.config import Settings, settings
from app.models.user import User
from helpers import auth, make_user

LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"


def login(client, email, password):
    return client.post(LOGIN, data={"username": email, "password": password})


# ---------------------------------------------------------------------------
# Băm mật khẩu
# ---------------------------------------------------------------------------
def test_password_hash_is_bcrypt_and_verifies():
    hashed = security.get_password_hash("mat-khau-123")
    assert hashed.startswith("$2")
    assert security.verify_password("mat-khau-123", hashed)
    assert not security.verify_password("mat-khau-124", hashed)
    assert not security.needs_rehash(hashed)


def test_same_password_gets_different_salts():
    assert security.get_password_hash("abc12345") != security.get_password_hash("abc12345")


def test_long_passwords_are_not_truncated_at_72_bytes():
    base = "x" * 80
    hashed = security.get_password_hash(base + "A")
    assert security.verify_password(base + "A", hashed)
    assert not security.verify_password(base + "B", hashed)


def test_unicode_password_roundtrip():
    hashed = security.get_password_hash("mậtkhẩu-tiếngViệt-🎾")
    assert security.verify_password("mậtkhẩu-tiếngViệt-🎾", hashed)


def test_legacy_sha256_hash_still_verifies_and_is_flagged_for_upgrade():
    legacy = security._legacy_hash("123456")
    assert security.needs_rehash(legacy)
    assert security.verify_password("123456", legacy)
    assert not security.verify_password("1234567", legacy)


@pytest.mark.parametrize("stored", ["", "not-a-hash", "$2b$12$tooshort"])
def test_verify_password_rejects_malformed_hashes(stored):
    assert security.verify_password("123456", stored) is False


def test_login_upgrades_legacy_hash_to_bcrypt(client, db):
    user = make_user(db, email="old@example.com")
    user.password_hash = security._legacy_hash("123456")
    db.commit()

    assert login(client, "old@example.com", "123456").status_code == 200
    db.expire_all()
    upgraded = db.get(User, user.id).password_hash
    assert upgraded.startswith("$2") and security.verify_password("123456", upgraded)
    assert login(client, "old@example.com", "123456").status_code == 200


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
def test_settings_require_a_real_secret_key():
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY="short", DATABASE_URL="postgresql://u:p@localhost/db", _env_file=None)
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY="please_change_in_production_123", DATABASE_URL="postgresql://u:p@localhost/db",
                 ENVIRONMENT="production", _env_file=None)


def test_settings_normalise_database_url_to_psycopg3():
    cfg = Settings(SECRET_KEY="k" * 32, DATABASE_URL="postgresql://u:p@localhost:5432/db", _env_file=None)
    assert cfg.DATABASE_URL == "postgresql+psycopg://u:p@localhost:5432/db"
    assert not cfg.is_sqlite


def test_cors_does_not_allow_lan_regex_in_production():
    dev = Settings(SECRET_KEY="k" * 32, DATABASE_URL="postgresql://u:p@h/db", _env_file=None)
    prod = Settings(SECRET_KEY="k" * 32, DATABASE_URL="postgresql://u:p@h/db", ENVIRONMENT="production", _env_file=None)
    assert dev.cors_origin_regex and prod.cors_origin_regex is None


# ---------------------------------------------------------------------------
# Đăng ký
# ---------------------------------------------------------------------------
def test_register_creates_player_without_fabricated_profile_data(client, db):
    response = client.post(REGISTER, json={"email": "New.Player@Example.Com", "password": "secret123", "full_name": " An "})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email"] == "new.player@example.com" and body["role"] == "PLAYER"
    profile = body["player_profile"]
    assert profile["full_name"] == "An"
    # Không gán sẵn số điện thoại, trình độ hay toạ độ giả
    assert profile["phone"] is None and profile["skill_level"] is None
    assert profile["latitude"] is None and profile["longitude"] is None
    assert profile["availability"] == [] and profile["preferred_amenity_ids"] == []
    assert "password" not in str(body).lower()


@pytest.mark.parametrize("role", ["OWNER", "ADMIN", "STAFF"])
def test_register_cannot_self_assign_privileged_role(client, role):
    response = client.post(REGISTER, json={"email": "x@example.com", "password": "secret123", "role": role})
    assert response.status_code == 403


def test_register_rejects_duplicate_email_case_insensitively(client, db):
    make_user(db, email="dup@example.com")
    response = client.post(REGISTER, json={"email": "DUP@example.com", "password": "secret123"})
    assert response.status_code == 400


@pytest.mark.parametrize("payload", [
    {"email": "not-an-email", "password": "secret123"},
    {"email": "a@example.com", "password": "123"},
    {"email": "a@example.com", "password": "secret123", "phone": "12ab"},
])
def test_register_validates_input(client, payload):
    assert client.post(REGISTER, json=payload).status_code == 422


def test_register_normalises_phone(client):
    response = client.post(REGISTER, json={"email": "p@example.com", "password": "secret123", "phone": "0901.234 567"})
    assert response.json()["player_profile"]["phone"] == "0901234567"


# ---------------------------------------------------------------------------
# Đăng nhập, token
# ---------------------------------------------------------------------------
def test_login_returns_token_that_authenticates(client, db):
    user = make_user(db, email="ok@example.com", password="secret123")
    response = login(client, "OK@example.com", "secret123")
    assert response.status_code == 200
    token = response.json()["access_token"]
    me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["id"] == user.id


def test_login_failure_does_not_reveal_whether_email_exists(client, db):
    make_user(db, email="real@example.com", password="secret123")
    wrong_password = login(client, "real@example.com", "nope-nope")
    unknown_email = login(client, "ghost@example.com", "nope-nope")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_tampered_foreign_and_expired_tokens_are_rejected(client, db):
    user = make_user(db)
    good = security.create_access_token(user.id)
    forged = jwt.encode({"sub": str(user.id)}, "another-secret-key-000000", algorithm="HS256")
    expired = security.create_access_token(user.id, expires_delta=timedelta(seconds=-5))
    for token in (good[:-3] + "abc", forged, expired, "garbage"):
        response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token


def test_token_for_deleted_user_is_rejected(client, db):
    user = make_user(db)
    headers = auth(user)
    db.delete(user.player_profile)
    db.delete(user)
    db.commit()
    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


def test_locked_account_cannot_login_and_existing_token_stops_working(client, db):
    user = make_user(db, email="locked@example.com", password="secret123")
    headers = auth(user)
    assert client.get("/api/v1/users/me", headers=headers).status_code == 200

    user.is_active = False
    db.commit()
    assert login(client, "locked@example.com", "secret123").status_code == 403
    assert client.get("/api/v1/users/me", headers=headers).status_code == 401


# ---------------------------------------------------------------------------
# Giới hạn đăng nhập sai
# ---------------------------------------------------------------------------
def test_login_is_blocked_after_too_many_failures(client, db):
    make_user(db, email="victim@example.com", password="secret123")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert login(client, "victim@example.com", "wrong").status_code == 401

    blocked = login(client, "victim@example.com", "secret123")  # đúng mật khẩu vẫn bị chặn trong thời gian khóa
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_rate_limit_is_per_account_and_resets_after_success(client, db):
    make_user(db, email="a@example.com", password="secret123")
    make_user(db, email="b@example.com", password="secret123")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        login(client, "a@example.com", "wrong")
    assert login(client, "b@example.com", "secret123").status_code == 200

    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        login(client, "b@example.com", "wrong")
    assert login(client, "b@example.com", "secret123").status_code == 200  # đăng nhập đúng xóa bộ đếm
    for _ in range(settings.LOGIN_MAX_ATTEMPTS - 1):
        assert login(client, "b@example.com", "wrong").status_code == 401


def test_rate_limit_window_expires(client, db, monkeypatch):
    make_user(db, email="w@example.com", password="secret123")
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        login(client, "w@example.com", "wrong")
    assert login(client, "w@example.com", "secret123").status_code == 429

    real_time = rate_limit.time.time

    class _Later:
        @staticmethod
        def time():
            return real_time() + settings.LOGIN_WINDOW_SECONDS + 1

    monkeypatch.setattr(rate_limit, "time", _Later)
    assert login(client, "w@example.com", "secret123").status_code == 200
