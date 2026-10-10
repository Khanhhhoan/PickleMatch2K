"""Tiện ích dùng chung cho các script quản trị CSDL."""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.database import engine  # noqa: E402
from app.db.migrations import alembic_config, migration_status, run_migrations  # noqa: E402,F401


def ensure_schema() -> None:
    """Tạo/cập nhật bảng mà không xóa dữ liệu."""
    if settings.is_sqlite:
        Base.metadata.create_all(bind=engine)
    else:
        run_migrations()


def confirm_destructive(action: str, assume_yes: bool = False) -> None:
    """Bắt người chạy xác nhận trước khi xóa dữ liệu. Bỏ qua bằng --yes hoặc PM2K_ASSUME_YES=1."""
    if assume_yes or "--yes" in sys.argv or os.getenv("PM2K_ASSUME_YES") == "1":
        return
    database = engine.url.database
    print(f"⚠️  {action} sẽ XÓA TOÀN BỘ dữ liệu trong CSDL '{database}'.")
    if not sys.stdin.isatty():
        raise SystemExit("Đã dừng: không có terminal để xác nhận. Thêm --yes nếu bạn chắc chắn.")
    typed = input(f"Gõ lại tên CSDL ({database}) để xác nhận: ").strip()
    if typed != database:
        raise SystemExit("Đã hủy thao tác.")


def rebuild_empty_schema(action: str, assume_yes: bool = False) -> None:
    """Xóa sạch và dựng lại schema trống (sau khi xác nhận)."""
    confirm_destructive(action, assume_yes)
    if settings.is_sqlite:
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        return
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    run_migrations()
