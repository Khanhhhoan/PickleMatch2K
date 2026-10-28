"""Hạ tầng: schema sau migration, tác vụ nền, WebSocket và script nạp dữ liệu demo."""
import json

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app.core.websocket_manager import to_public_event
from app.db.base import Base
from app.db.database import engine
from app.main import api_docs_urls, app
from app.models.booking import Booking
from app.models.match import Match
from app.models.payment import PaymentTransaction
from app.models.user import User
from app.models.venue import Review
from app.services import maintenance
from helpers import auth, confirmed_booking, create_booking, slot

WS = "/api/v1/ws"


# ---------------------------------------------------------------------------
# Tài liệu API
# ---------------------------------------------------------------------------
def test_api_docs_are_closed_in_production_and_open_elsewhere(client):
    assert api_docs_urls(True) == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert api_docs_urls(False) == {}
    for path in ("/docs", "/redoc", "/openapi.json"):     # môi trường kiểm thử không phải production
        assert client.get(path).status_code == 200


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def test_migrations_produce_exactly_the_schema_the_models_describe():
    with engine.connect() as conn:
        differences = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert differences == []

    from scripts._common import BACKEND_DIR
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == [current]  # một nhánh migration duy nhất và CSDL đang ở bản mới nhất


def test_database_level_guards_exist():
    with engine.connect() as conn:
        constraints = {row[0] for row in conn.execute(text(
            "SELECT conname FROM pg_constraint WHERE connamespace = 'public'::regnamespace"))}
        indexes = {row[0]: row[1] for row in conn.execute(text(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'"))}
        sequences = {row[0] for row in conn.execute(text(
            "SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'"))}

    assert {"ex_booking_details_no_overlap", "ck_booking_details_time_order", "uq_match_participants_match_user",
            "uq_operating_hours_venue_day", "uq_reviews_user_venue"} <= constraints
    assert "UNIQUE" in indexes["uq_booking_details_active_slot"] and "WHERE is_active" in indexes["uq_booking_details_active_slot"]
    assert "UNIQUE" in indexes["uq_payment_transactions_reference"]
    assert {"booking_code_seq", "transaction_code_seq"} <= sequences


# ---------------------------------------------------------------------------
# Tác vụ nền
# ---------------------------------------------------------------------------
def test_maintenance_run_expires_finalises_and_closes_matches(client, db, world, clock):
    day = clock.day(1)
    unpaid = create_booking(client, world.p1, world.court, day, hours=(9,))
    absent = confirmed_booking(client, world.p2, world.venue_a.courts[1], day, hours=(9,))
    match = client.post("/api/v1/matches", json={"booking_id": absent["id"]}, headers=auth(world.p2)).json()

    clock.set(day, 10, 5)
    maintenance.run_maintenance_once()

    db.expire_all()
    assert db.get(Booking, unpaid["id"]).status == "EXPIRED"
    assert db.get(Booking, absent["id"]).status == "NO_SHOW"
    assert db.get(Match, match["id"]).status == "CANCELLED"


def test_maintenance_skips_a_round_while_another_process_runs_one(client, db, world, clock):
    """Nhiều tiến trình API: chỉ một tiến trình chạy lượt bảo trì tại một thời điểm, nhờ khóa tư vấn của PostgreSQL."""
    unpaid = create_booking(client, world.p1, world.court, clock.day(1), hours=(9,))
    clock.advance(minutes=20)

    with engine.connect() as other_process:
        other_process.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": maintenance.MAINTENANCE_LOCK_KEY})
        assert maintenance.run_maintenance_once() is False
        db.expire_all()
        assert db.get(Booking, unpaid["id"]).status == "PENDING"
    # Tiến trình kia xong lượt (giao dịch kết thúc, khóa tự nhả): lượt sau chạy bình thường
    assert maintenance.run_maintenance_once() is True
    db.expire_all()
    assert db.get(Booking, unpaid["id"]).status == "EXPIRED"


def test_background_jobs_skip_rows_another_transaction_is_working_on(client, db, world, clock):
    from app.db.database import SessionLocal
    from app.services import booking_service, match_service

    day = clock.day(1)
    absent = confirmed_booking(client, world.p1, world.court, day, hours=(9,))
    room = client.post("/api/v1/matches", json={"booking_id": confirmed_booking(
        client, world.p2, world.venue_a.courts[1], day, hours=(9,))["id"]}, headers=auth(world.p2)).json()
    clock.set(day, 10, 5)

    # Phòng đấu đang bị giao dịch khác giữ: lượt này bỏ qua, lượt sau mới xử lý
    with SessionLocal() as other:
        other.execute(text("SELECT id FROM matches WHERE id = :id FOR UPDATE"), {"id": room["id"]})
        assert match_service.auto_update_expired_matches(db) == []
        other.rollback()
    assert [m["id"] for m in match_service.auto_update_expired_matches(db)] == [room["id"]]
    assert match_service.auto_update_expired_matches(db) == []      # lượt sau không xử lý lại

    # Đơn đang bị giao dịch khác giữ (ví dụ nhân viên đang thao tác): lượt này bỏ qua đơn đó
    with SessionLocal() as other:
        other.execute(text("SELECT id FROM bookings WHERE id = :id FOR UPDATE"), {"id": absent["id"]})
        assert absent["id"] not in booking_service.finalize_past_bookings(db)
        other.rollback()
    assert booking_service.finalize_past_bookings(db) == [absent["id"]]
    assert booking_service.finalize_past_bookings(db) == []          # lượt sau không xử lý lại


def test_one_failing_job_does_not_stop_the_others(client, db, world, clock, monkeypatch):
    from app.services import booking_service

    unpaid = create_booking(client, world.p1, world.court, clock.day(1), hours=(9,))
    clock.advance(minutes=20)

    def broken(_db):
        raise RuntimeError("boom")

    monkeypatch.setattr(booking_service, "finalize_past_bookings", broken)
    maintenance.run_maintenance_once()   # không ném lỗi ra ngoài

    db.expire_all()
    assert db.get(Booking, unpaid["id"]).status == "EXPIRED"


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
def test_public_events_are_stripped_of_personal_and_financial_fields():
    event = to_public_event({
        "type": "SLOT_BOOKED", "venue_id": 1, "booking_id": 5, "status": "PENDING", "message": "x",
        "user_id": 7, "user_name": "Nguyễn A", "user_phone": "0900", "user_email": "a@b.c", "total_price": 300000,
        "slots": [{"court_id": 1, "date": "2030-01-01", "start_time": "18:00", "end_time": "19:00", "is_available": False,
                   "held_by": "Nguyễn A", "price": 150000}, "garbage"],
    })
    assert set(event) == {"type", "venue_id", "booking_id", "status", "message", "slots"}
    assert event["slots"] == [{"court_id": 1, "date": "2030-01-01", "start_time": "18:00", "end_time": "19:00",
                               "is_available": False}]


def test_private_channel_requires_the_owners_token(client, world):
    def connect(user_id, token=None):
        url = f"{WS}/user/{user_id}" + (f"?token={token}" if token else "")
        with client.websocket_connect(url) as socket:
            return socket.receive_json()

    token_p1 = auth(world.p1)["Authorization"].split()[1]
    assert connect(world.p1.id, token_p1) == {"type": "USER_CHANNEL_SUBSCRIBED", "user_id": world.p1.id}
    for user_id, token in ((world.p1.id, None), (world.p1.id, "garbage"), (world.p2.id, token_p1)):
        with pytest.raises(WebSocketDisconnect) as closed:
            connect(user_id, token)
        assert closed.value.code == 1008


def drain(socket) -> list:
    """Đọc các sự kiện đã phát cho tới khi nhận 'pong' (để test không treo nếu không có sự kiện nào)."""
    socket.send_text("ping")
    events = []
    while True:
        message = socket.receive_text()
        if message == "pong":
            return events
        events.append(json.loads(message))


def test_booking_events_reach_venue_and_global_channels_without_private_data(db, world, clock):
    day = clock.day(1)
    with TestClient(app) as live:   # chạy lifespan để gắn vòng lặp sự kiện cho việc phát WebSocket
        with live.websocket_connect(f"{WS}/venues/{world.venue_a.id}") as venue_socket, \
                live.websocket_connect(f"{WS}/venues/{world.venue_b.id}") as other_venue, \
                live.websocket_connect(f"{WS}/live") as global_socket:
            assert venue_socket.receive_json() == {"type": "VENUE_SUBSCRIBED", "venue_id": world.venue_a.id}
            other_venue.receive_json()
            assert global_socket.receive_json() == {"type": "CONNECTION_ESTABLISHED"}

            response = live.post("/api/v1/bookings", json={"details": [slot(world.court, day, 18)]}, headers=auth(world.p1))
            assert response.status_code == 200

            venue_events, global_events = drain(venue_socket), drain(global_socket)
            assert drain(other_venue) == []                                   # cụm sân khác không nhận sự kiện

    [booked] = venue_events
    assert booked["type"] == "SLOT_BOOKED" and booked["venue_id"] == world.venue_a.id
    assert booked["slots"] == [{"court_id": world.court.id, "court_name": "Sân 1", "date": day.isoformat(),
                                "start_time": "18:00:00", "end_time": "19:00:00", "is_available": False}]
    assert {e["type"] for e in global_events} == {"SLOT_BOOKED", "BOOKING_STATUS_CHANGED"}
    dump = json.dumps(venue_events + global_events)
    for private in (world.p1.email, world.p1.player_profile.phone, world.p1.player_profile.full_name, "150000"):
        assert private not in dump


# ---------------------------------------------------------------------------
# Dữ liệu demo
# ---------------------------------------------------------------------------
def test_demo_seed_builds_a_consistent_dataset(client, db):
    from scripts import seed

    assert seed.seed_database() is True
    assert seed.seed_database(if_empty=True) is False       # chạy lại không nạp trùng
    with pytest.raises(SystemExit):
        seed.seed_database()

    roles = dict(db.execute(text("SELECT role, count(*) FROM users GROUP BY role")).all())
    assert roles == {"ADMIN": 1, "OWNER": 3, "STAFF": 9, "PLAYER": 20}
    assert db.execute(text("SELECT count(*) FROM courts")).scalar() == 21

    statuses = dict(db.execute(text("SELECT status, count(*) FROM bookings GROUP BY status")).all())
    assert statuses == {"COMPLETED": 7, "NO_SHOW": 1, "CANCELLED": 2, "CONFIRMED": 5}
    # Số tiền đã trả của mỗi đơn khớp đúng với sổ giao dịch
    mismatched = db.execute(text("""
        SELECT b.booking_code FROM bookings b
        LEFT JOIN payment_transactions t ON t.booking_id = b.id AND t.kind IN ('DEPOSIT', 'BALANCE')
        GROUP BY b.id HAVING abs(b.paid_amount - coalesce(sum(t.amount_in), 0)) > 0.5
    """)).all()
    assert mismatched == []
    assert db.query(PaymentTransaction).filter_by(kind="REFUND").count() == 1
    assert db.query(Booking).filter_by(refund_status="PENDING").count() == 1

    # Mọi đánh giá đều đến từ người đã thật sự chơi xong tại cụm sân đó
    fake_reviews = db.execute(text("""
        SELECT r.id FROM reviews r WHERE NOT EXISTS (
            SELECT 1 FROM bookings b JOIN booking_details d ON d.booking_id = b.id JOIN courts c ON c.id = d.court_id
            WHERE b.user_id = r.user_id AND b.status = 'COMPLETED' AND c.venue_id = r.venue_id)
    """)).all()
    assert fake_reviews == [] and db.query(Review).count() == 6
    assert dict(db.execute(text("SELECT status, count(*) FROM matches GROUP BY status")).all()) == {"OPEN": 2, "FULL": 1}
    assert db.execute(text("SELECT count(*) FROM player_profiles WHERE purpose IS NULL")).scalar() == 0

    for email in ("admin@example.com", "owner_rudal@pickleball.vn", "staff_152no_3@pickleball.vn", "player18@gmail.com"):
        login = client.post("/api/v1/auth/login", data={"username": email, "password": seed.DEMO_PASSWORD})
        assert login.status_code == 200, email

    player = db.query(User).filter_by(email="khanhhoan121209@gmail.com").one()
    partners = client.get("/api/v1/ml/recommend-partners", headers=auth(player)).json()
    assert partners["missing_profile_fields"] == [] and len(partners["items"]) == 8
    venues = client.get("/api/v1/recommendations/venues", headers=auth(player)).json()
    assert len(venues) == 3 and all(v["criteria_used"] == ["distance", "price", "time"] for v in venues)
    assert seed.apply_demo_preferences(db) == 0             # không ghi đè mục đích chơi đã có


def test_match_demo_adds_rooms_to_a_database_in_use_without_touching_what_is_there(client, db):
    """`python manage.py seed --matches`: thêm người chơi và phòng đấu mẫu để thử ghép trận, chạy lại được."""
    from scripts import seed

    seed.seed_database()
    fingerprint = text("""
        SELECT md5(string_agg(concat_ws('|', u.id, u.email, u.is_active, p.skill_level, p.play_style, p.purpose,
                                        p.latitude, p.longitude, p.phone), ';' ORDER BY u.id))
        FROM users u LEFT JOIN player_profiles p ON p.user_id = u.id WHERE u.email NOT LIKE 'ghep%@example.com'
    """)
    existing_accounts = db.execute(fingerprint).scalar()
    existing_bookings = db.execute(text("SELECT count(*), coalesce(sum(paid_amount), 0) FROM bookings")).one()
    existing_rooms = {row[0] for row in db.execute(text("SELECT id FROM matches")).all()}

    result = seed.seed_match_demo(db)

    assert result["players"] == 12 and len(result["rooms"]) == 10 and result["skipped"] == []
    db.expire_all()
    assert db.execute(fingerprint).scalar() == existing_accounts              # tài khoản có sẵn không bị sửa
    new_rooms = db.query(Match).filter(Match.id.notin_(existing_rooms)).all()
    assert sorted(room.status for room in new_rooms) == ["FULL"] + ["OPEN"] * 9
    assert sorted({room.creator.player_profile.skill_level for room in new_rooms}) == [2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    assert any(len(room.participants) == room.num_players - 1 for room in new_rooms)   # có phòng còn đúng 1 chỗ
    for room in new_rooms:                                                    # mỗi phòng có sân thật, đã cọc
        assert room.creator.email.startswith("ghep") and room.booking.status == "CONFIRMED"
        assert room.booking.paid_amount == room.booking.deposit_amount > 0
        assert all(p.user.email.startswith("ghep") for p in room.participants)

    deposits = db.query(PaymentTransaction).filter(PaymentTransaction.gateway == seed.MATCH_DEMO_GATEWAY).all()
    assert len(deposits) == 10 and all(t.reference_number.startswith("DEMO-PK2K") for t in deposits)
    after = db.execute(text("SELECT count(*), coalesce(sum(paid_amount), 0) FROM bookings")).one()
    assert after[0] == existing_bookings[0] + 10 and after[1] == existing_bookings[1] + sum(t.amount_in for t in deposits)
    clashes = db.execute(text("""
        SELECT count(*) FROM match_participants a JOIN matches ma ON ma.id = a.match_id
        JOIN match_participants b ON b.user_id = a.user_id AND b.match_id > a.match_id JOIN matches mb ON mb.id = b.match_id
        WHERE ma.status IN ('OPEN', 'FULL') AND mb.status IN ('OPEN', 'FULL')
          AND ma.date = mb.date AND ma.start_time < mb.end_time AND mb.start_time < ma.end_time
    """)).scalar()
    assert clashes == 0                                                       # không ai ở hai phòng trùng giờ

    # Người chơi có sẵn mở trang ghép trận: có phòng được mô hình đề xuất, có phòng không
    viewer = db.query(User).filter_by(email="player@example.com").one()       # trình 3.5
    rooms = [m for m in client.get("/api/v1/matches", headers=auth(viewer)).json() if m["id"] not in existing_rooms]
    joinable = [m for m in rooms if m["status"] == "OPEN"]
    assert len(rooms) == 10 and len(joinable) == 9
    assert {m["is_recommended"] for m in joinable} == {True, False}
    login = client.post("/api/v1/auth/login", data={"username": "ghep01@example.com", "password": seed.DEMO_PASSWORD})
    assert login.status_code == 200
    mine = client.get("/api/v1/ml/model-info", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
    assert mine["missing_profile_fields"] == []                               # hồ sơ mẫu đầy đủ cho mô hình

    again = seed.seed_match_demo(db)                                          # chạy lại: không nạp trùng
    assert again["players"] == 0 and again["rooms"] == [] and len(again["skipped"]) == 10
    assert db.query(Match).count() == len(existing_rooms) + 10


# ---------------------------------------------------------------------------
# Script quản trị
# ---------------------------------------------------------------------------
def write_excel(path, rows):
    import pandas as pd

    columns = ["STT", "Tên Cụm Sân (*)", "Quận / Huyện (*)", "Địa Chỉ Chi Tiết (*)",
               "Danh Sách Sân Con (*)\n(Phân cách dấu phẩy)", "Giá Thường\n(VNĐ/Giờ)", "Giá Cao Điểm\n(VNĐ/Giờ)",
               "Giá Cuối Tuần\n(VNĐ/Giờ)", "Giờ Mở Cửa", "Giờ Đóng Cửa", "Họ Tên Chủ Sân",
               "Email Chủ Sân (*)\n(Dùng đăng nhập)", "Số Điện Thoại", "Tài Khoản Ngân Hàng",
               "Tiện Ích Có Sẵn\n(Phân cách dấu phẩy)", "Mô Tả Cụm Sân", "Link Google Maps\n(Tùy chọn)",
               "Link Ảnh Sân\n(Tùy chọn)"]
    pd.DataFrame(rows, columns=columns).to_excel(path, sheet_name="1. Danh_Sach_Cum_San", index=False)
    return path


def test_excel_import_adds_venues_and_reports_incomplete_rows_instead_of_inventing_data(client, db, tmp_path):
    from app.models.venue import Venue
    from scripts.import_excel import import_from_excel

    excel = write_excel(tmp_path / "venues.xlsx", [
        [1, "CLB Lan Anh", "Quận 10", "291 Cách Mạng Tháng 8", "Sân VIP, Sân 1, Sân 2", 160000, 230000, 250000,
         "06:00", "23:00", "Lê Lan Anh", "Owner_LanAnh@pickleball.vn", 901234567, "0901234567 - MBBank",
         "Đèn LED 500 Lux, Sân có mái che, Bãi đỗ xe ô tô", "Mô tả", "https://maps.google.com/?q=10.7788,106.6775", None],
        [2, "Sân Không Toạ Độ", "Quận 7", "12 Tân Thuận Tây", "Sân 1", 150000, None, None, "5h30", "22:00",
         None, "owner_q7@pickleball.vn", None, None, None, None, "https://maps.app.goo.gl/abc", None],
        [3, "Sân Thiếu Email", "Quận 1", "1 Lê Lợi", "Sân 1", 150000, None, None, "06:00", "22:00",
         None, None, None, None, None, None, None, None],
        [4, "Sân Thiếu Giá", "Quận 3", "2 Võ Văn Tần", "Sân 1", None, None, None, "06:00", "22:00",
         None, "owner_q3@pickleball.vn", None, None, None, None, None, None],
    ])

    preview = import_from_excel(excel, dry_run=True, password="imported-pw")
    assert preview["imported"] == 2 and db.query(Venue).count() == 0        # chạy thử không ghi gì

    summary = import_from_excel(excel, password="imported-pw")
    assert summary["imported"] == 2
    assert [(line, name) for line, name, _ in summary["skipped"]] == [(4, "Sân Thiếu Email"), (5, "Sân Thiếu Giá")]
    assert [email for email, _ in summary["accounts"]] == ["owner_lananh@pickleball.vn", "owner_q7@pickleball.vn"]

    first = db.query(Venue).filter_by(name="CLB Lan Anh").one()
    assert (first.latitude, first.longitude, first.status) == (10.7788, 106.6775, "ACTIVE")
    assert [c.name for c in first.courts] == ["Sân VIP", "Sân 1", "Sân 2"] and len(first.operating_hours) == 7
    assert {r.rule_type: r.price for r in first.price_rules} == {"BASE": 160000, "PEAK": 230000, "WEEKEND": 250000}
    assert len(first.amenities) == 3
    owner = first.owner.owner_profile
    assert (owner.full_name, owner.phone, owner.bank_account) == ("Lê Lan Anh", "0901234567", "0901234567 - MBBank")

    second = db.query(Venue).filter_by(name="Sân Không Toạ Độ").one()
    assert second.latitude is None and second.longitude is None             # không bịa toạ độ
    assert second.owner.owner_profile.phone is None and second.owner.owner_profile.bank_account is None
    assert second.operating_hours[0].open_time.strftime("%H:%M") == "05:30"
    assert {r.rule_type: r.price for r in second.price_rules} == {"BASE": 150000, "PEAK": 150000, "WEEKEND": 150000}

    login = client.post("/api/v1/auth/login", data={"username": "owner_lananh@pickleball.vn", "password": "imported-pw"})
    assert login.status_code == 200

    again = import_from_excel(excel)                                         # chạy lại không tạo bản trùng
    assert again["imported"] == 2 and again["accounts"] == []
    db.expire_all()
    assert db.query(Venue).count() == 2 and len(db.query(Venue).filter_by(name="CLB Lan Anh").one().courts) == 3


def test_venue_activity_fills_a_newly_added_venue_and_leaves_everything_else_alone(client, db, tmp_path, monkeypatch):
    """`python manage.py seed --activity`: cụm sân vừa nhập thêm có nhân viên, đơn, giao dịch, phòng đấu, đánh giá mẫu."""
    from app.models.venue import Venue
    from app.services import booking_service
    from scripts import seed
    from scripts.import_excel import import_from_excel

    seed.seed_database()
    import_from_excel(write_excel(tmp_path / "new_venue.xlsx", [
        [1, "Sân Mới Gò Vấp", "Gò Vấp", "2 Lê Đức Thọ", "Sân 1, Sân 2, Sân 3, Sân 4", 130000, 180000, 130000,
         "05:00", "22:00", "Chủ Sân Mới", "owner_sanmoi@pickleball.vn", None, None, "Bãi đỗ xe ô tô", "Mô tả",
         "https://maps.google.com/?q=10.83,106.68", None],
    ]), password=seed.DEMO_PASSWORD)
    venue = db.query(Venue).filter_by(name="Sân Mới Gò Vấp").one()

    tables = ("users", "bookings", "payment_transactions", "matches", "match_participants", "reviews")
    count_rows = text("SELECT " + ", ".join(f"(SELECT count(*) FROM {table})" for table in tables))
    last_ids = dict(db.execute(text("""
        SELECT 'u', coalesce(max(id), 0) FROM users UNION ALL SELECT 'b', coalesce(max(id), 0) FROM bookings
        UNION ALL SELECT 't', coalesce(max(id), 0) FROM payment_transactions
        UNION ALL SELECT 'm', coalesce(max(id), 0) FROM matches UNION ALL SELECT 'r', coalesce(max(id), 0) FROM reviews
    """)).all())
    fingerprint = text("""
        SELECT md5(concat_ws('#',
            (SELECT string_agg(concat_ws('|', id, email, role, is_active), ';' ORDER BY id) FROM users WHERE id <= :u),
            (SELECT string_agg(concat_ws('|', id, status, payment_status, paid_amount, refund_status, created_at), ';' ORDER BY id)
               FROM bookings WHERE id <= :b),
            (SELECT string_agg(concat_ws('|', id, booking_id, kind, gateway, amount_in, transaction_content), ';' ORDER BY id)
               FROM payment_transactions WHERE id <= :t),
            (SELECT string_agg(concat_ws('|', id, status, num_players), ';' ORDER BY id) FROM matches WHERE id <= :m),
            (SELECT string_agg(concat_ws('|', match_id, user_id), ';' ORDER BY match_id, user_id)
               FROM match_participants WHERE match_id <= :m),
            (SELECT string_agg(concat_ws('|', id, user_id, venue_id, rating, comment), ';' ORDER BY id) FROM reviews WHERE id <= :r)))
    """)
    rows_before, data_before = tuple(db.execute(count_rows).one()), db.execute(fingerprint, last_ids).scalar()
    db.rollback()

    # Hỏng giữa chừng thì không ghi gì: cả lượt nạp nằm trong một giao dịch
    def lost_connection(*args, **kwargs):
        raise RuntimeError("mất kết nối giữa chừng")

    monkeypatch.setattr(booking_service, "confirm_refund", lost_connection)
    with pytest.raises(RuntimeError):
        seed.add_venue_activity(venue.id)
    monkeypatch.undo()
    assert tuple(db.execute(count_rows).one()) == rows_before
    db.rollback()

    result = seed.add_venue_activity(venue.id)

    assert result["skipped"] == [] and len(result["venues"]) == 1
    item = result["venues"][0]
    # Chạy sau 20h thì khung giờ tối nay không còn đặt được: đó là lượt duy nhất được phép thiếu
    assert len(item["skipped"]) <= 1 and all("đã qua" in reason for reason in item["skipped"])
    tonight = 1 - len(item["skipped"])
    assert item["statuses"] == {"COMPLETED": 6, "NO_SHOW": 1, "CANCELLED": 2, "CONFIRMED": 4 + tonight}
    assert (item["bookings"], item["rooms"], item["reviews"]) == (13 + tonight, 2, 5)
    assert item["owner"] == "owner_sanmoi@pickleball.vn"
    assert item["staff"] == ["staff_sanmoi_1@pickleball.vn", "staff_sanmoi_2@pickleball.vn"]

    db.expire_all()
    assert db.execute(fingerprint, last_ids).scalar() == data_before          # dữ liệu có từ trước không bị sửa
    added = [after - before for after, before in zip(db.execute(count_rows).one(), rows_before)]
    assert added == [2, 13 + tonight, 18 + tonight, 2, 3, 5]                  # tài khoản, đơn, giao dịch, phòng, thành viên, đánh giá

    here = "(SELECT d.booking_id FROM booking_details d JOIN courts c ON c.id = d.court_id WHERE c.venue_id = :venue)"
    scope = {"venue": venue.id}
    at_venue = dict(db.execute(text(f"SELECT status, count(*) FROM bookings WHERE id IN {here} GROUP BY status"), scope).all())
    assert at_venue == item["statuses"]
    mismatched = db.execute(text("""
        SELECT b.booking_code FROM bookings b
        LEFT JOIN payment_transactions t ON t.booking_id = b.id AND t.kind IN ('DEPOSIT', 'BALANCE')
        GROUP BY b.id HAVING abs(b.paid_amount - coalesce(sum(t.amount_in), 0)) > 0.5
    """)).all()
    assert mismatched == []                                                   # số tiền đã trả khớp sổ giao dịch
    ledger_rows = db.execute(text(f"""
        SELECT kind, gateway, coalesce(reference_number, ''), coalesce(transaction_content, '')
        FROM payment_transactions WHERE booking_id IN {here}
    """), scope).all()
    # Dòng nào cũng nhận ra được là dữ liệu mẫu: cọc chuyển khoản mang nhãn riêng, các dòng còn lại có ghi chú
    assert all((gateway == seed.MATCH_DEMO_GATEWAY and reference.startswith("DEMO-PK2K")) or content.endswith(seed.DEMO_NOTE)
               for _, gateway, reference, content in ledger_rows)
    assert sorted(kind for kind, *_ in ledger_rows) == ["BALANCE"] * 5 + ["DEPOSIT"] * (12 + tonight) + ["REFUND"]
    refunds = dict(db.execute(text(f"""
        SELECT refund_status, count(*) FROM bookings WHERE id IN {here} AND refund_status IS NOT NULL GROUP BY refund_status
    """), scope).all())
    assert refunds == {"COMPLETED": 1, "PENDING": 1}
    # Đơn đã qua được ghi đúng thời điểm trong quá khứ, không phải lúc chạy lệnh
    late = db.execute(text(f"""
        SELECT count(*) FROM bookings b WHERE b.id IN {here} AND b.status IN ('COMPLETED', 'NO_SHOW')
          AND b.created_at > (SELECT min(d.date + d.start_time) FROM booking_details d WHERE d.booking_id = b.id) AT TIME ZONE 'Asia/Ho_Chi_Minh'
    """), scope).scalar()
    assert late == 0

    reviews = db.query(Review).filter_by(venue_id=venue.id).all()
    assert sorted(r.rating for r in reviews) == [4.0, 4.0, 5.0, 5.0, 5.0]
    fake_reviews = db.execute(text("""
        SELECT r.id FROM reviews r WHERE NOT EXISTS (
            SELECT 1 FROM bookings b JOIN booking_details d ON d.booking_id = b.id JOIN courts c ON c.id = d.court_id
            WHERE b.user_id = r.user_id AND b.status = 'COMPLETED' AND c.venue_id = r.venue_id)
    """)).all()
    assert fake_reviews == []
    rooms = db.query(Match).filter_by(venue_id=venue.id).order_by(Match.date).all()
    assert [(room.status, len(room.participants), room.num_players) for room in rooms] == [("OPEN", 1, 2), ("OPEN", 2, 4)]
    assert all(room.booking.status == "CONFIRMED" and room.booking.paid_amount == room.booking.deposit_amount for room in rooms)

    # Nhân viên mới đăng nhập được và thấy đơn của đúng cụm sân mình
    login = client.post("/api/v1/auth/login", data={"username": item["staff"][0], "password": seed.DEMO_PASSWORD})
    assert login.status_code == 200
    staff = db.query(User).filter_by(email=item["staff"][0]).one()
    assert staff.staff_profile.venue_id == venue.id
    viewer = db.query(User).filter_by(email="player@example.com").one()
    listed = [m for m in client.get("/api/v1/matches", headers=auth(viewer)).json() if m["venue_id"] == venue.id]
    assert len(listed) == 2

    again = seed.add_venue_activity(venue.id)                                 # chạy lại: không nạp trùng
    assert again["venues"] == [] and len(again["skipped"]) == 1
    assert seed.add_venue_activity() == {"venues": [], "skipped": []}         # không còn cụm sân nào chưa có đơn
    db.rollback()
    assert [after - before for after, before in zip(db.execute(count_rows).one(), rows_before)] == added


def test_destructive_scripts_refuse_to_run_without_confirmation(db, world):
    from scripts._common import rebuild_empty_schema

    with pytest.raises(SystemExit):
        rebuild_empty_schema("Thử xóa")          # không có terminal để xác nhận và không có --yes
    assert db.query(User).count() == 8           # dữ liệu còn nguyên


def test_reset_leaves_an_empty_migrated_database_with_one_admin(client, db, world):
    from scripts.reset_db import reset_database

    db.rollback()
    reset_database(admin_email="root@example.com", admin_password="first-password", assume_yes=True)

    counts = {table: db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
              for table in ("users", "venues", "bookings", "amenities")}
    assert counts == {"users": 1, "venues": 0, "bookings": 0, "amenities": 8}
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata) == []
    login = client.post("/api/v1/auth/login", data={"username": "root@example.com", "password": "first-password"})
    assert login.status_code == 200


# ---------------------------------------------------------------------------
# Nâng cấp schema (python manage.py migrate)
# ---------------------------------------------------------------------------
def _rebuild_schema(revision: str = "head") -> None:
    from alembic import command

    from app.db.migrations import alembic_config

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(), revision)


@pytest.fixture
def legacy_database(db):
    """CSDL như trước khi dự án dùng Alembic: schema của revision 0001, có dữ liệu, không có bảng alembic_version."""
    db.rollback()
    _rebuild_schema("0001")
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
        conn.execute(text("INSERT INTO users (email, password_hash, role, is_active) VALUES ('old@example.com', 'x', 'PLAYER', true)"))
    yield
    _rebuild_schema()   # các test sau cần schema mới nhất


def _assert_migrated_with_data_intact() -> None:
    from app.db.migrations import migration_status

    status = migration_status()
    assert status["current"] == status["head"] and not status["legacy"] and not status["pending"] and not status["unknown"]
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata) == []
        assert conn.execute(text("SELECT email FROM users")).scalar() == "old@example.com"


def test_migrate_upgrades_a_database_created_before_alembic_without_losing_data(legacy_database):
    from app.db.migrations import migration_status, run_migrations

    status = migration_status()
    assert status["legacy"] is True and status["pending"] is True and status["empty"] is False

    run_migrations()

    _assert_migrated_with_data_intact()


def test_migrate_backs_up_first_and_changes_nothing_when_the_backup_fails(legacy_database, monkeypatch, tmp_path, capsys):
    import manage
    from app.db.migrations import migration_status
    from scripts import backup_db

    def failing_backup():
        raise FileNotFoundError("Không tìm thấy pg_dump")

    monkeypatch.setattr(backup_db, "backup", failing_backup)
    with pytest.raises(SystemExit) as stopped:
        manage.migrate()
    assert "Chưa thay đổi gì" in str(stopped.value)
    assert migration_status()["legacy"] is True          # schema còn nguyên

    calls = []
    monkeypatch.setattr(backup_db, "backup", lambda: calls.append("backup") or tmp_path / "x.dump")
    manage.migrate()
    assert calls == ["backup"]
    assert "x.dump" in capsys.readouterr().out            # in sẵn lệnh khôi phục
    _assert_migrated_with_data_intact()

    manage.migrate()                                      # chạy lại: không còn gì để làm, không sao lưu thêm
    assert calls == ["backup"]


def test_migrate_check_only_reports_and_the_api_refuses_to_start_on_an_old_schema(legacy_database):
    import manage
    from app.db.migrations import migration_status, require_current_schema

    with pytest.raises(SystemExit) as stopped:
        manage.migrate(check_only=True)
    assert stopped.value.code == manage.EXIT_MIGRATION_PENDING
    assert migration_status()["legacy"] is True          # --check không thay đổi gì

    with pytest.raises(RuntimeError, match="python manage.py migrate"):
        require_current_schema()
    with pytest.raises(RuntimeError, match="python manage.py migrate"):
        with TestClient(app):                             # lifespan dừng ngay, không chạy trên schema cũ
            pass

    manage.migrate(backup_first=False)
    require_current_schema()
    manage.migrate(check_only=True)                       # đã mới nhất: không còn mã thoát 3
    _assert_migrated_with_data_intact()


def test_dropping_free_time_keeps_real_survey_answers_and_clears_only_the_simulated_sheets(db):
    """Migration 0005: hai cột giờ rảnh bị bỏ; phiếu mô phỏng cũ bị xóa để nạp lại, câu trả lời khảo sát thật còn nguyên."""
    from alembic import command

    from app.db.migrations import alembic_config, run_migrations

    def columns(table):
        with engine.connect() as conn:
            return {row[0] for row in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = :t"), {"t": table})}

    db.rollback()
    _rebuild_schema("0004")
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (email, password_hash, role, is_active) VALUES ('old@example.com', 'x', 'PLAYER', true)"))
            conn.execute(text("INSERT INTO player_profiles (user_id, skill_level, purpose, availability) "
                              "VALUES (1, 3.5, 'practice', '[\"mon_evening\"]')"))
            conn.execute(text(
                "INSERT INTO pair_feedback (rater_id, source, level_diff, distance_km, availability_overlap, purpose_match, style_match, label) "
                "VALUES (1, 'survey', 0.5, 3, 0.4, 1, 0, 1), (1, 'simulated', 1.5, 9, 0.1, 0, 0, 0)"))

        run_migrations()

        _assert_migrated_with_data_intact()
        assert "availability" not in columns("player_profiles") and "availability_overlap" not in columns("pair_feedback")
        assert not {"preferred_amenities", "budget_max"} & columns("player_profiles")      # migration 0006
        assert "avatar_url" in columns("player_profiles")
        with engine.connect() as conn:
            assert [tuple(row) for row in conn.execute(text(
                "SELECT source, level_diff, distance_km, purpose_match, style_match, label FROM pair_feedback"))] == [("survey", 0.5, 3.0, 1, 0, 1)]
            assert tuple(conn.execute(text("SELECT skill_level, purpose FROM player_profiles")).one()) == (3.5, "practice")

        command.downgrade(alembic_config(), "0004")          # quay lại được: cột có lại, dữ liệu còn lại không mất
        assert "availability" in columns("player_profiles") and "availability_overlap" in columns("pair_feedback")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*), max(availability_overlap) FROM pair_feedback")).one() == (1, 0.0)
    finally:
        _rebuild_schema()   # các test sau cần schema mới nhất


def test_adding_the_age_criterion_keeps_real_survey_answers_and_clears_only_the_simulated_sheets(db):
    """Migration 0007: bảng phiếu có thêm chênh lệch tuổi; phiếu mô phỏng cũ bị xóa để nạp lại, câu trả lời thật còn nguyên."""
    from alembic import command

    from app.db.migrations import alembic_config, run_migrations
    from app.ml import train_model
    from app.services import ml_service

    db.rollback()
    _rebuild_schema("0006")
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (email, password_hash, role, is_active) VALUES ('old@example.com', 'x', 'PLAYER', true)"))
            conn.execute(text(
                "INSERT INTO pair_feedback (rater_id, source, level_diff, distance_km, purpose_match, style_match, label) "
                "VALUES (1, 'survey', 0.5, 3, 1, 0, 1), (1, 'simulated', 1.5, 9, 0, 0, 0)"))

        run_migrations()

        _assert_migrated_with_data_intact()
        with engine.connect() as conn:
            assert [tuple(row) for row in conn.execute(text(
                "SELECT source, level_diff, distance_km, purpose_match, style_match, age_diff, label FROM pair_feedback"
            ))] == [("survey", 0.5, 3.0, 1, 0, None, 1)]
        # câu trả lời cũ không có chênh lệch tuổi: còn trong bảng, nhưng không được tính và không tham gia huấn luyện
        assert ml_service.feedback_summary(db)["labels"] == 0
        db.rollback()
        assert len(train_model.load_real_feedback()) == 0

        command.downgrade(alembic_config(), "0006")          # quay lại được, câu trả lời thật không mất
        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM pair_feedback")).scalar() == 1
    finally:
        _rebuild_schema()   # các test sau cần schema mới nhất


def test_moving_refund_proofs_into_the_database_copies_the_files_already_on_disk(db):
    """Migration 0013: tệp chứng từ đang nằm trên ổ đĩa được chép vào bảng refund_proofs; hạ cấp ghi lại ra ổ đĩa."""
    import uuid

    from alembic import command

    from app.db.migrations import alembic_config, run_migrations
    from scripts._common import BACKEND_DIR

    proof_dir = BACKEND_DIR / "private_uploads" / "refund_proofs"
    created = [folder for folder in (proof_dir.parent, proof_dir) if not folder.exists()]
    on_disk, missing = f"1_{uuid.uuid4().hex}.png", f"2_{uuid.uuid4().hex}.pdf"
    content = b"\x89PNG\r\n\x1a\nchung tu cu"

    db.rollback()
    _rebuild_schema("0012")
    try:
        proof_dir.mkdir(parents=True, exist_ok=True)
        (proof_dir / on_disk).write_bytes(content)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (email, password_hash, role, is_active) VALUES ('old@example.com', 'x', 'PLAYER', true)"))
            conn.execute(text("INSERT INTO bookings (user_id, total_price, refund_proof_file) VALUES (1, 0, :a), (1, 0, :b)"),
                         {"a": on_disk, "b": missing})

        run_migrations()

        _assert_migrated_with_data_intact()
        with engine.connect() as conn:
            stored = [(row.booking_id, row.name, row.media_type, row.size, bytes(row.content)) for row in conn.execute(text(
                "SELECT booking_id, name, media_type, size, content FROM refund_proofs"))]
            assert stored == [(1, on_disk, "image/png", len(content), content)]
            # tệp không còn trên máy này: đơn giữ nguyên tên chứng từ, không có dòng nội dung
            assert conn.execute(text("SELECT refund_proof_file FROM bookings WHERE id = 2")).scalar() == missing

        (proof_dir / on_disk).unlink()
        command.downgrade(alembic_config(), "0012")          # quay lại được: nội dung được ghi lại ra ổ đĩa
        assert (proof_dir / on_disk).read_bytes() == content
    finally:
        for name in (on_disk, missing):
            (proof_dir / name).unlink(missing_ok=True)
        for folder in reversed(created):
            try:
                folder.rmdir()
            except OSError:
                pass
        _rebuild_schema()   # các test sau cần schema mới nhất


def test_a_database_newer_than_the_code_is_reported_instead_of_migrated(db):
    import manage
    from app.db.migrations import migration_status, require_current_schema

    db.rollback()
    head = migration_status()["head"]
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = '9999_future'"))
        assert migration_status()["unknown"] is True
        with pytest.raises(SystemExit, match="git pull"):
            manage.migrate()
        with pytest.raises(RuntimeError, match="git pull"):
            require_current_schema()
    finally:
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": head})
