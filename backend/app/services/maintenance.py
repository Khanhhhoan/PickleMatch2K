"""Tác vụ nền định kỳ: hết hạn đơn chưa cọc, kết thúc đơn và phòng đấu đã qua giờ."""
import logging

from app.db.database import SessionLocal

logger = logging.getLogger("pickleball.maintenance")


def run_maintenance_once() -> None:
    """Chạy một lượt bảo trì. Hàm đồng bộ: gọi qua asyncio.to_thread để không chặn event loop."""
    from app.services.booking_service import expire_stale_pending, finalize_past_bookings
    from app.services.match_service import auto_update_expired_matches

    db = SessionLocal()
    try:
        for job in (expire_stale_pending, finalize_past_bookings, auto_update_expired_matches):
            try:
                job(db)
            except Exception:
                db.rollback()
                logger.exception("Tác vụ nền %s thất bại", job.__name__)
    finally:
        db.close()
