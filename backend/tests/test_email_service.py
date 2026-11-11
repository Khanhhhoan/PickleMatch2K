"""Gửi thư: ghi vào thư mục outbox khi chạy ở máy, test và demo; gửi qua API HTTPS của Brevo khi chạy thật."""
import httpx
import pytest

from app.core.config import settings
from app.services import email_service
from app.services.email_service import EmailMessage, email_ready, send_email

SENDER = "gui-thu@pickle2k.vn"
MESSAGE = EmailMessage(
    to="an.nguyen@mailbox.vn",
    subject="Đặt lại mật khẩu PickleMatch2K",
    text="Mở liên kết để đặt lại mật khẩu.",
    html="<p>Mở liên kết để đặt lại mật khẩu.</p>",
)


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = '{"message": "trả lời giả"}'


@pytest.fixture
def brevo(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "khoa-brevo-gia")
    monkeypatch.setattr(settings, "EMAIL_FROM", SENDER)
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "PickleMatch2K")


def test_file_backend_writes_one_json_message(outbox):
    assert send_email(MESSAGE) is True

    mails = outbox()
    assert len(mails) == 1
    assert {field: mails[0][field] for field in ("to", "subject", "text", "html")} == {
        "to": MESSAGE.to, "subject": MESSAGE.subject, "text": MESSAGE.text, "html": MESSAGE.html,
    }
    assert mails[0]["created_at"]


def test_brevo_backend_posts_the_expected_request(brevo, monkeypatch, outbox):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(201)

    monkeypatch.setattr(email_service.httpx, "post", fake_post)

    assert send_email(MESSAGE) is True

    (url, kwargs), = calls
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert kwargs["headers"]["api-key"] == "khoa-brevo-gia"
    body = kwargs["json"]
    assert body["sender"] == {"name": "PickleMatch2K", "email": SENDER}
    assert body["to"] == [{"email": MESSAGE.to}]
    assert (body["subject"], body["textContent"], body["htmlContent"]) == (MESSAGE.subject, MESSAGE.text, MESSAGE.html)
    assert outbox() == []  # Brevo gửi thì không ghi gì ra thư mục


def test_brevo_failure_returns_false_without_raising(brevo, monkeypatch):
    def timeout(url, **kwargs):
        raise httpx.ConnectTimeout("hết thời gian chờ")

    monkeypatch.setattr(email_service.httpx, "post", timeout)
    assert send_email(MESSAGE) is False

    monkeypatch.setattr(email_service.httpx, "post", lambda url, **kwargs: FakeResponse(401))
    assert send_email(MESSAGE) is False


def test_email_ready_rules(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "file")
    assert email_ready() is True

    monkeypatch.setattr(settings, "EMAIL_BACKEND", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", None)
    monkeypatch.setattr(settings, "EMAIL_FROM", SENDER)
    assert email_ready() is False

    monkeypatch.setattr(settings, "BREVO_API_KEY", "khoa-brevo-gia")
    monkeypatch.setattr(settings, "EMAIL_FROM", "")
    assert email_ready() is False

    monkeypatch.setattr(settings, "EMAIL_FROM", SENDER)
    assert email_ready() is True


def test_file_backend_is_not_ready_in_production(monkeypatch):
    """Bản chạy thật quên đặt EMAIL_BACKEND=brevo: thư không được ghi lặng lẽ ra ổ đĩa của máy chủ."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "file")

    assert email_ready() is False
