"""
Cấu hình pytest của backend.

Toàn bộ test chạy trên một CSDL PostgreSQL RIÊNG có tên kết thúc bằng `_test`:
- mặc định: CSDL `pickleball_test` trên cùng máy chủ/tài khoản với DATABASE_URL trong .env;
- hoặc đặt biến môi trường TEST_DATABASE_URL=postgresql://user:pass@host:5432/<tên>_test.
CSDL đang dùng thật KHÔNG bao giờ bị đụng tới: việc trỏ sang CSDL test diễn ra trước khi ứng dụng tạo engine.

Mỗi phiên test dựng lại schema bằng chính các migration Alembic; mỗi test bắt đầu với các bảng trống
và đồng hồ nghiệp vụ đứng ở 08:00 (giờ Việt Nam) của ngày hôm nay.
"""
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import List

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
for _path in (str(BACKEND_DIR), str(Path(__file__).resolve().parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.core.config import settings  # noqa: E402
from helpers import TEST_BANK_ACCOUNT, WEBHOOK_KEY, make_user, make_venue  # noqa: E402


def _resolve_test_url() -> URL:
    configured = make_url(settings.DATABASE_URL)
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        for prefix in ("postgresql://", "postgres://"):
            if explicit.startswith(prefix):
                explicit = "postgresql+psycopg://" + explicit[len(prefix):]
        url = make_url(explicit)
    else:
        if configured.get_backend_name() != "postgresql":
            raise pytest.UsageError(
                "Bộ test cần PostgreSQL. Đặt TEST_DATABASE_URL=postgresql://user:pass@host:5432/pickleball_test"
            )
        url = configured.set(database="pickleball_test")
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        raise pytest.UsageError("CSDL dùng cho test phải là PostgreSQL và có tên kết thúc bằng '_test'.")
    if (url.host, url.port, url.database) == (configured.host, configured.port, configured.database):
        raise pytest.UsageError("CSDL test trùng với CSDL đang cấu hình trong DATABASE_URL: dừng để tránh mất dữ liệu.")
    return url


TEST_URL = _resolve_test_url()

# Phải gán trước khi bất kỳ module nào của ứng dụng import app.db.database
settings.DATABASE_URL = TEST_URL.render_as_string(hide_password=False)
settings.ENVIRONMENT = "test"
settings.BCRYPT_ROUNDS = 4
settings.LOGIN_MAX_ATTEMPTS = 5
settings.LOGIN_WINDOW_SECONDS = 300
settings.REDIS_URL = None
settings.STORAGE_BACKEND = "local"
settings.CLOUDINARY_CLOUD_NAME = settings.CLOUDINARY_API_KEY = settings.CLOUDINARY_API_SECRET = None
settings.SEPAY_WEBHOOK_API_KEY = WEBHOOK_KEY
settings.SEPAY_UNIFIED_TEST_MODE = True
settings.SEPAY_SIMULATOR_ENABLED = True
settings.SEPAY_BANK_ACCOUNT = TEST_BANK_ACCOUNT
settings.SEPAY_BANK_CODE = "MB"
settings.SEPAY_BANK_NAME = "MBBank"
settings.SEPAY_ACCOUNT_HOLDER = "TAI KHOAN KIEM THU"

from app.utils import timeutils  # noqa: E402
from app.utils.timeutils import VN_TZ, vn_datetime  # noqa: E402

REAL_TODAY = datetime.now(VN_TZ).date()


# ---------------------------------------------------------------------------
# CSDL
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def _database():
    """Tạo CSDL test nếu chưa có, rồi dựng lại schema từ đầu bằng migration."""
    admin = create_engine(TEST_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_URL.database}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_URL.database}"'))
    admin.dispose()

    from app.db.database import engine
    from scripts._common import run_migrations

    assert engine.url.database == TEST_URL.database
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    run_migrations()
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_state(_database):
    from app.core.rate_limit import login_rate_limiter
    from app.db.base import Base
    from app.db.database import engine
    from app.services.slot_lock_service import slot_lock_manager

    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '15s'"))  # phiên bị bỏ quên thì báo lỗi thay vì treo
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE booking_code_seq RESTART WITH 1"))
        conn.execute(text("ALTER SEQUENCE transaction_code_seq RESTART WITH 1"))
    slot_lock_manager.clear_memory()
    login_rate_limiter.clear_all()
    yield


@pytest.fixture
def db(_clean_state):
    """Phiên CSDL để chuẩn bị và kiểm tra dữ liệu. Gọi db.expire_all() trước khi đọc lại sau một lệnh API."""
    from app.db.database import SessionLocal

    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# Đồng hồ nghiệp vụ
# ---------------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.moment = vn_datetime(REAL_TODAY, time(8, 0))

    def __call__(self) -> datetime:
        return self.moment

    @property
    def today(self) -> date:
        return self.moment.date()

    def set(self, day: date, hour: int, minute: int = 0) -> None:
        self.moment = vn_datetime(day, time(hour, minute))

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)

    def day(self, offset: int) -> date:
        return self.today + timedelta(days=offset)


@pytest.fixture(autouse=True)
def clock():
    """Đồng hồ nghiệp vụ đứng yên; test chủ động tua bằng clock.set(...) / clock.advance(...)."""
    frozen = Clock()
    timeutils.set_clock(frozen)
    yield frozen
    timeutils.set_clock(None)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------
@pytest.fixture
def client(_clean_state):
    """Client không chạy lifespan: không có tác vụ nền và không phát WebSocket."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Dữ liệu nền dùng chung
# ---------------------------------------------------------------------------
@dataclass
class World:
    admin: object
    owner_a: object
    owner_b: object
    staff_a: object
    staff_b: object
    venue_a: object
    venue_b: object
    players: List[object]

    @property
    def p1(self):
        return self.players[0]

    @property
    def p2(self):
        return self.players[1]

    @property
    def p3(self):
        return self.players[2]

    @property
    def court(self):
        return self.venue_a.courts[0]


@pytest.fixture
def world(db) -> World:
    """Hai cụm sân của hai chủ sân khác nhau, mỗi cụm một nhân viên, cùng một admin và ba người chơi."""
    admin = make_user(db, "ADMIN", "admin@example.com")
    owner_a = make_user(db, "OWNER", "owner_a@example.com", bank_account="111222333 - MBBank", company_name="CHU SAN A")
    owner_b = make_user(db, "OWNER", "owner_b@example.com", bank_account="444555666 - Vietcombank", company_name="CHU SAN B")
    venue_a = make_venue(db, owner_a, name="Sân A")
    venue_b = make_venue(db, owner_b, name="Sân B", base=200000, peak=260000, lat=10.85, lng=106.75)
    staff_a = make_user(db, "STAFF", "staff_a@example.com", venue=venue_a)
    staff_b = make_user(db, "STAFF", "staff_b@example.com", venue=venue_b)
    players = [
        make_user(db, "PLAYER", f"p{i}@example.com", phone=f"09000000{i}", skill_level=3.5, latitude=10.78, longitude=106.70)
        for i in (1, 2, 3)
    ]
    return World(admin, owner_a, owner_b, staff_a, staff_b, venue_a, venue_b, players)
