import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.websocket_manager import manager
from app.db.database import check_database_connection, engine
from app.db.migrations import require_current_schema
from app.services.maintenance import run_maintenance_once

logger = logging.getLogger("pickleball")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-5s [%(name)s] %(message)s")

MAINTENANCE_INTERVAL_SECONDS = 60


async def periodic_status_updater():
    """Mỗi 60 giây: hết hạn đơn chưa cọc, hoàn tất đơn và phòng đấu đã qua giờ."""
    while True:
        try:
            await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
            await asyncio.to_thread(run_maintenance_once)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Vòng lặp tác vụ nền gặp lỗi")


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_database_connection()
    if settings.is_sqlite:
        # SQLite chỉ dành cho thử nhanh trên máy cá nhân: tạo bảng trực tiếp từ model.
        # PostgreSQL luôn dùng migration: `alembic upgrade head`.
        from app.db.base import Base
        Base.metadata.create_all(bind=engine)
    else:
        require_current_schema()
    if not settings.SEPAY_WEBHOOK_API_KEY:
        logger.warning("SEPAY_WEBHOOK_API_KEY chưa được cấu hình: webhook SePay chưa được xác thực.")

    manager.bind_loop(asyncio.get_running_loop())
    await asyncio.to_thread(run_maintenance_once)
    task = asyncio.create_task(periodic_status_updater())
    yield
    task.cancel()


def api_docs_urls(production: bool) -> dict:
    """Bản production không công bố tài liệu API (Swagger, ReDoc, lược đồ OpenAPI); chạy trên máy thì vẫn mở."""
    if production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


app = FastAPI(
    title="Pickleball Booking API",
    description="API for Pickleball Booking System with ML Integration",
    version="1.0.0",
    lifespan=lifespan,
    **api_docs_urls(settings.is_production),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ảnh sân lưu cục bộ được phục vụ tại /uploads
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(os.path.join(UPLOAD_DIR, "venues"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "message": "Backend is running smoothly"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
