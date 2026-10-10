"""Phiên bản schema (Alembic) của CSDL đang cấu hình: đọc trạng thái, nâng cấp, và chặn chạy trên schema cũ."""
from pathlib import Path

from sqlalchemy import inspect, text

from app.db.database import engine

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Revision mô tả đúng schema của các CSDL được tạo trước khi dự án dùng Alembic (bằng create_all)
LEGACY_BASELINE_REVISION = "0001"


def alembic_config():
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["configure_logger"] = False
    return cfg


def migration_status() -> dict:
    """
    current: revision đang ghi trong CSDL (None nếu chưa có); head: revision mới nhất của mã nguồn.
    legacy: có bảng nghiệp vụ nhưng chưa có dấu Alembic; unknown: CSDL ở revision mà mã nguồn này không có.
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config())
    head = script.get_current_head()
    known = {revision.revision for revision in script.walk_revisions()}
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar() if "alembic_version" in tables else None
    return {
        "current": current,
        "head": head,
        "legacy": current is None and "users" in tables,
        "empty": not (tables - {"alembic_version"}),
        "unknown": current is not None and current not in known,
        "pending": current != head,
    }


def describe_current(status: dict) -> str:
    if status["current"]:
        return status["current"]
    return "chưa dùng Alembic" if status["legacy"] else "trống"


def run_migrations() -> None:
    """
    Đưa schema PostgreSQL lên phiên bản mới nhất (tương đương `alembic upgrade head`).
    CSDL có từ trước khi dùng Alembic được đánh dấu ở revision gốc rồi mới nâng cấp, nên dữ liệu cũ được giữ.
    """
    from alembic import command

    cfg = alembic_config()
    if migration_status()["legacy"]:
        print(f"CSDL được tạo trước khi dùng Alembic: đánh dấu revision {LEGACY_BASELINE_REVISION} rồi nâng cấp.")
        command.stamp(cfg, LEGACY_BASELINE_REVISION)
    command.upgrade(cfg, "head")


def require_current_schema() -> None:
    """Dừng ngay lúc khởi động với hướng dẫn rõ ràng, thay vì để từng API lỗi vì thiếu cột/bảng."""
    status = migration_status()
    if status["unknown"]:
        raise RuntimeError(
            f"CSDL '{engine.url.database}' đang ở revision {status['current']} mà mã nguồn này không có. "
            "Hãy cập nhật mã nguồn lên bản mới nhất (git pull) rồi chạy lại."
        )
    if status["pending"]:
        raise RuntimeError(
            f"Schema của CSDL '{engine.url.database}' ({describe_current(status)}) chưa ở phiên bản mã nguồn cần ({status['head']}). "
            "Chạy trong thư mục backend/: python manage.py migrate"
        )
