"""
Tác vụ nền định kỳ: hết hạn đơn chưa cọc, kết thúc đơn và phòng đấu đã qua giờ.

Mỗi tiến trình API có một vòng lặp gọi hàm này, nên khi chạy nhiều tiến trình (uvicorn --workers N) các lượt có thể
trùng nhau. Hai lớp bảo vệ:
1. Mỗi lượt giữ một khóa tư vấn (advisory lock) của PostgreSQL theo giao dịch, trên một kết nối riêng. Tiến trình
   không giành được khóa thì bỏ qua lượt đó; khóa tự nhả khi giao dịch kết thúc, kể cả khi tiến trình chết giữa chừng.
2. Bên trong, mỗi tác vụ khóa dòng với SKIP LOCKED: dù có ai chạy tay song song, một đơn hay một phòng đấu cũng chỉ
   được xử lý một lần, nên không có thông báo hay yêu cầu hoàn tiền trùng.
"""
import logging

from sqlalchemy import text

from app.db.database import SessionLocal, engine

logger = logging.getLogger("pickleball.maintenance")

# Khóa tư vấn dùng chung cho mọi tiến trình API: một số nguyên cố định bất kỳ
MAINTENANCE_LOCK_KEY = 72_026_001


def _try_lock(connection) -> bool:
    """Giành khóa của lượt bảo trì trong giao dịch hiện tại của `connection`; không chờ nếu đang có người giữ."""
    if connection.dialect.name != "postgresql":
        return True  # SQLite chỉ dùng thử trên một máy với một tiến trình
    return bool(connection.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": MAINTENANCE_LOCK_KEY}).scalar())


def run_maintenance_once() -> bool:
    """
    Chạy một lượt bảo trì. Trả về False nếu tiến trình khác đang chạy lượt của nó (lượt này được bỏ qua).
    Hàm đồng bộ: gọi qua asyncio.to_thread để không chặn event loop.
    """
    from app.services.booking_service import expire_stale_pending, finalize_past_bookings, release_unpaid_desk_bookings
    from app.services.match_service import auto_update_expired_matches

    with engine.connect() as lock_connection:
        if not _try_lock(lock_connection):
            logger.info("Bỏ qua lượt tác vụ nền: một tiến trình khác đang chạy lượt của nó.")
            return False
        db = SessionLocal()
        try:
            for job in (expire_stale_pending, release_unpaid_desk_bookings, finalize_past_bookings, auto_update_expired_matches):
                try:
                    job(db)
                except Exception:
                    db.rollback()
                    logger.exception("Tác vụ nền %s thất bại", job.__name__)
        finally:
            db.close()
        # Rời khối `with`: giao dịch của lock_connection được hủy và khóa tư vấn tự nhả
    return True
