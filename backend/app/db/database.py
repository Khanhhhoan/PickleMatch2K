import logging

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger("pickleball.db")


def _build_engine():
    url = settings.DATABASE_URL
    if settings.is_sqlite:
        sqlite_engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(sqlite_engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return sqlite_engine
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)


engine = _build_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def check_database_connection() -> None:
    """Dừng hẳn khi không kết nối được CSDL đã cấu hình, không âm thầm đổi sang CSDL khác."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(
            f"Không kết nối được CSDL ({engine.url.render_as_string(hide_password=True)}). "
            "Kiểm tra DATABASE_URL và dịch vụ PostgreSQL."
        ) from exc
    logger.info("Đã kết nối CSDL: %s", engine.url.render_as_string(hide_password=True))
