import asyncio
import json
import logging
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger("pickleball.websocket")

# Kênh /ws/live và /ws/venues/{id} là kênh công khai (không cần đăng nhập), nên chỉ các trường
# dưới đây được phép phát ra. Tên, số điện thoại, số tiền, user_id... bị loại bỏ tại đây.
PUBLIC_EVENT_FIELDS = {
    "type", "message", "venue_id", "venue_name", "booking_id", "match_id", "court_id", "court_name",
    "date", "start_time", "end_time", "slots", "status", "payment_status", "refund_status",
    "participants_count", "num_players", "is_full", "expire_in_seconds",
    "rule_type", "price", "base_price", "peak_price", "weekend_price",
}
PUBLIC_SLOT_FIELDS = {"court_id", "court_name", "date", "start_time", "end_time", "is_available"}


def to_public_event(message: dict) -> dict:
    """Lọc sự kiện trước khi phát lên kênh công khai."""
    event = {k: v for k, v in message.items() if k in PUBLIC_EVENT_FIELDS}
    if isinstance(event.get("slots"), list):
        event["slots"] = [
            {k: v for k, v in slot.items() if k in PUBLIC_SLOT_FIELDS}
            for slot in event["slots"] if isinstance(slot, dict)
        ]
    return event


class ConnectionManager:
    def __init__(self):
        # Vòng lặp sự kiện chính của ứng dụng, được gắn khi khởi động (xem main.lifespan)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.global_connections: List[WebSocket] = []
        self.venue_connections: Dict[int, List[WebSocket]] = {}
        self.user_connections: Dict[int, List[WebSocket]] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect_global(self, websocket: WebSocket):
        await websocket.accept()
        self.global_connections.append(websocket)

    def disconnect_global(self, websocket: WebSocket):
        if websocket in self.global_connections:
            self.global_connections.remove(websocket)

    async def connect_venue(self, venue_id: int, websocket: WebSocket):
        await websocket.accept()
        self.venue_connections.setdefault(venue_id, []).append(websocket)

    def disconnect_venue(self, venue_id: int, websocket: WebSocket):
        connections = self.venue_connections.get(venue_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.venue_connections.pop(venue_id, None)

    async def connect_user(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.user_connections.setdefault(user_id, []).append(websocket)

    def disconnect_user(self, user_id: int, websocket: WebSocket):
        connections = self.user_connections.get(user_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            self.user_connections.pop(user_id, None)

    async def _send_all(self, connections: List[WebSocket], payload: str) -> List[WebSocket]:
        dead = []
        for connection in list(connections):
            try:
                await connection.send_text(payload)
            except Exception:
                dead.append(connection)
        return dead

    async def broadcast_global(self, message: dict):
        """Phát sự kiện (đã lọc) tới mọi client đang nghe kênh công khai."""
        payload = json.dumps(to_public_event(message), default=str)
        for dc in await self._send_all(self.global_connections, payload):
            self.disconnect_global(dc)

    async def broadcast_venue_event(self, venue_id: int, message: dict):
        """Phát sự kiện (đã lọc) tới người đang xem lịch của một cụm sân và kênh công khai."""
        payload = json.dumps(to_public_event(message), default=str)
        for dc in await self._send_all(self.venue_connections.get(venue_id, []), payload):
            self.disconnect_venue(venue_id, dc)
        for dc in await self._send_all(self.global_connections, payload):
            self.disconnect_global(dc)

    async def send_to_user(self, user_id: int, message: dict):
        """Gửi thông báo riêng (không lọc) tới đúng người dùng đã xác thực."""
        payload = json.dumps(message, default=str)
        for dc in await self._send_all(self.user_connections.get(user_id, []), payload):
            self.disconnect_user(user_id, dc)


# Global singleton
manager = ConnectionManager()


def dispatch(coro) -> None:
    """
    Lên lịch một coroutine phát WebSocket từ bất kỳ đâu.
    Endpoint đồng bộ của FastAPI chạy trong thread pool, nên coroutine phải được đưa về
    đúng vòng lặp sự kiện chính thay vì tạo vòng lặp mới trong thread đó.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is not None:
        running.create_task(coro)
    elif manager.loop is not None and manager.loop.is_running():
        asyncio.run_coroutine_threadsafe(coro, manager.loop)
    else:
        # Không có server đang chạy (script, test đơn vị): bỏ qua sự kiện
        coro.close()
