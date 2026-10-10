import logging
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.api.deps import get_user_from_token
from app.core.websocket_manager import manager
from app.db.database import SessionLocal

router = APIRouter()
logger = logging.getLogger("pickleball.ws_router")


async def _keep_alive(websocket: WebSocket) -> None:
    """Giữ kết nối mở và trả lời ping của client."""
    while True:
        data = await websocket.receive_text()
        if data == "ping":
            await websocket.send_text("pong")


@router.websocket("/live")
async def websocket_global_live(websocket: WebSocket):
    """
    Kênh công khai (không cần đăng nhập): chỉ nhận sự kiện đã lọc, không chứa thông tin cá nhân
    (xem PUBLIC_EVENT_FIELDS). Client dùng làm tín hiệu để tải lại dữ liệu qua REST API có xác thực.
    """
    await manager.connect_global(websocket)
    try:
        await websocket.send_json({"type": "CONNECTION_ESTABLISHED"})
        await _keep_alive(websocket)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS live error: %s", exc)
    finally:
        manager.disconnect_global(websocket)


@router.websocket("/venues/{venue_id}")
async def websocket_venue_availability(websocket: WebSocket, venue_id: int):
    """Kênh công khai theo cụm sân: đồng bộ trạng thái slot (đặt, giữ chỗ, giải phóng)."""
    await manager.connect_venue(venue_id, websocket)
    try:
        await websocket.send_json({"type": "VENUE_SUBSCRIBED", "venue_id": venue_id})
        await _keep_alive(websocket)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS venue %s error: %s", venue_id, exc)
    finally:
        manager.disconnect_venue(venue_id, websocket)


@router.websocket("/user/{user_id}")
async def websocket_user_channel(websocket: WebSocket, user_id: int, token: Optional[str] = Query(None)):
    """
    Kênh riêng của từng người dùng: bắt buộc có access token hợp lệ của chính người đó
    (?token=...). Dùng cho thông báo cá nhân có thể chứa thông tin riêng tư.
    """
    db = SessionLocal()
    try:
        user = get_user_from_token(db, token)
        authorised = user is not None and user.id == user_id
    finally:
        db.close()
    if not authorised:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect_user(user_id, websocket)
    try:
        await websocket.send_json({"type": "USER_CHANNEL_SUBSCRIBED", "user_id": user_id})
        await _keep_alive(websocket)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS user %s error: %s", user_id, exc)
    finally:
        manager.disconnect_user(user_id, websocket)
