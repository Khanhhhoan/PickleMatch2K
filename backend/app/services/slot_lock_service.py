"""
Giữ chỗ tạm thời (5 phút) cho slot mà người chơi đang chọn, trước khi tạo đơn.

Dữ liệu lưu trong Redis (SET NX EX) khi có REDIS_URL, nên đúng cả khi chạy nhiều tiến trình.
Không có Redis thì lưu trong bộ nhớ của tiến trình (chỉ phù hợp khi chạy 1 worker).
Giữ chỗ chỉ là lớp trải nghiệm; việc chống đặt trùng thật sự do ràng buộc ở CSDL bảo đảm.
"""
import json
import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from app.core.booking_policy import MAX_HELD_SLOTS_PER_USER, SLOT_HOLD_SECONDS
from app.core.redis_client import get_redis
from app.core.websocket_manager import dispatch, manager

logger = logging.getLogger("pickleball.slot_lock")


def normalise_time(value: str) -> str:
    """'18:00:00' và '18:00' là cùng một slot."""
    return str(value)[:5]


def hold_key(court_id: int, slot_date: str, start_time: str) -> str:
    return f"hold:{int(court_id)}:{slot_date}:{normalise_time(start_time)}"


class MemoryHoldStore:
    def __init__(self):
        self._holds: Dict[str, Tuple[dict, float]] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.time()
        for key in [k for k, (_, expire_at) in self._holds.items() if expire_at <= now]:
            self._holds.pop(key, None)

    def acquire(self, key: str, payload: dict, ttl: int) -> Tuple[bool, Optional[dict], int]:
        """Trả về (thành công, thông tin người đang giữ nếu thất bại, số giây còn lại)."""
        with self._lock:
            self._purge()
            existing = self._holds.get(key)
            if existing and existing[0]["user_id"] != payload["user_id"]:
                return False, existing[0], max(1, int(existing[1] - time.time()))
            self._holds[key] = (payload, time.time() + ttl)
            return True, None, ttl

    def get(self, key: str) -> Optional[dict]:
        with self._lock:
            self._purge()
            existing = self._holds.get(key)
            return existing[0] if existing else None

    def delete(self, key: str, payload: Optional[dict] = None) -> None:
        with self._lock:
            self._holds.pop(key, None)

    def list_for_venue(self, venue_id: int, slot_date: str) -> List[dict]:
        with self._lock:
            self._purge()
            now = time.time()
            return [
                {**p, "seconds_remaining": max(0, int(expire_at - now))}
                for p, expire_at in self._holds.values()
                if p["venue_id"] == venue_id and p["date"] == slot_date
            ]

    def count_for_user(self, user_id: int) -> int:
        with self._lock:
            self._purge()
            return sum(1 for p, _ in self._holds.values() if p["user_id"] == user_id)

    def clear(self) -> None:
        with self._lock:
            self._holds.clear()


class RedisHoldStore:
    """Mỗi hold là một key có TTL; hai tập chỉ mục (theo cụm sân/ngày và theo người dùng) để liệt kê."""

    def __init__(self, client):
        self.client = client

    @staticmethod
    def _venue_index(venue_id: int, slot_date: str) -> str:
        return f"holds:venue:{venue_id}:{slot_date}"

    @staticmethod
    def _user_index(user_id: int) -> str:
        return f"holds:user:{user_id}"

    def acquire(self, key: str, payload: dict, ttl: int) -> Tuple[bool, Optional[dict], int]:
        raw = json.dumps(payload)
        if not self.client.set(key, raw, nx=True, ex=ttl):
            existing = self.get(key)
            if existing is None:
                # Hold cũ vừa hết hạn giữa hai lệnh: thử lại một lần
                if not self.client.set(key, raw, nx=True, ex=ttl):
                    return False, None, 1
            elif existing["user_id"] != payload["user_id"]:
                return False, existing, max(1, int(self.client.ttl(key)))
            else:
                self.client.set(key, raw, ex=ttl)  # cùng người: gia hạn
        for index in (self._venue_index(payload["venue_id"], payload["date"]), self._user_index(payload["user_id"])):
            self.client.sadd(index, key)
            self.client.expire(index, 86400)
        return True, None, ttl

    def get(self, key: str) -> Optional[dict]:
        raw = self.client.get(key)
        return json.loads(raw) if raw else None

    def delete(self, key: str, payload: Optional[dict] = None) -> None:
        payload = payload or self.get(key)
        self.client.delete(key)
        if payload:
            self.client.srem(self._venue_index(payload["venue_id"], payload["date"]), key)
            self.client.srem(self._user_index(payload["user_id"]), key)

    def _live_members(self, index: str) -> List[Tuple[str, dict]]:
        live = []
        for key in list(self.client.smembers(index)):
            payload = self.get(key)
            if payload is None:
                self.client.srem(index, key)  # hold đã hết hạn
            else:
                live.append((key, payload))
        return live

    def list_for_venue(self, venue_id: int, slot_date: str) -> List[dict]:
        return [
            {**payload, "seconds_remaining": max(0, int(self.client.ttl(key)))}
            for key, payload in self._live_members(self._venue_index(venue_id, slot_date))
        ]

    def count_for_user(self, user_id: int) -> int:
        return len(self._live_members(self._user_index(user_id)))

    def clear(self) -> None:
        pass


class SlotLockManager:
    def __init__(self):
        self._memory = MemoryHoldStore()

    def _store(self):
        client = get_redis()
        return RedisHoldStore(client) if client is not None else self._memory

    def _run(self, operation: str, *args, **kwargs):
        """Chạy thao tác trên Redis; nếu Redis lỗi giữa chừng thì dùng bộ nhớ thay vì làm hỏng yêu cầu."""
        store = self._store()
        try:
            return getattr(store, operation)(*args, **kwargs)
        except Exception as exc:
            if store is self._memory:
                raise
            logger.warning("Redis lỗi khi %s (%s): dùng bộ nhớ tiến trình.", operation, exc)
            return getattr(self._memory, operation)(*args, **kwargs)

    def hold_slot(
        self,
        venue_id: int,
        court_id: int,
        court_name: str,
        slot_date: str,
        start_time: str,
        end_time: str,
        user_id: int,
        hold_seconds: int = SLOT_HOLD_SECONDS,
    ) -> Tuple[bool, str]:
        key = hold_key(court_id, slot_date, start_time)
        current = self._run("get", key)
        is_refresh = current is not None and current["user_id"] == user_id
        if not is_refresh and self._run("count_for_user", user_id) >= MAX_HELD_SLOTS_PER_USER:
            return False, f"Bạn chỉ có thể giữ tạm tối đa {MAX_HELD_SLOTS_PER_USER} khung giờ cùng lúc."

        payload = {
            "venue_id": int(venue_id),
            "court_id": int(court_id),
            "date": str(slot_date),
            "start_time": normalise_time(start_time),
            "end_time": normalise_time(end_time),
            "user_id": int(user_id),
        }
        ok, _, remaining = self._run("acquire", key, payload, hold_seconds)
        if not ok:
            return False, f"Khung giờ này đang được người chơi khác tạm giữ (còn {remaining} giây)."

        dispatch(manager.broadcast_venue_event(venue_id, {
            "type": "SLOT_HELD",
            "venue_id": venue_id,
            "date": str(slot_date),
            "court_id": court_id,
            "court_name": court_name,
            "start_time": payload["start_time"],
            "end_time": payload["end_time"],
            "expire_in_seconds": hold_seconds,
            "message": f"{court_name} ({payload['start_time']}-{payload['end_time']}) đang được tạm giữ.",
        }))
        return True, "Đã giữ chỗ trong 5 phút để bạn hoàn tất đặt sân."

    def release_slot(self, venue_id: int, court_id: int, slot_date: str, start_time: str, user_id: int) -> bool:
        key = hold_key(court_id, slot_date, start_time)
        payload = self._run("get", key)
        if payload is None or payload["user_id"] != user_id:
            return False
        self._run("delete", key, payload)
        dispatch(manager.broadcast_venue_event(payload["venue_id"], {
            "type": "SLOT_RELEASED",
            "venue_id": payload["venue_id"],
            "date": payload["date"],
            "slots": [{
                "court_id": payload["court_id"],
                "date": payload["date"],
                "start_time": payload["start_time"],
                "end_time": payload["end_time"],
                "is_available": True,
            }],
            "message": f"Khung giờ {payload['start_time']}-{payload['end_time']} đã được trả lại.",
        }))
        return True

    def release_after_booking(self, court_id: int, slot_date: str, start_time: str) -> None:
        """Gỡ hold khi slot đã được ghi thành đơn đặt trong CSDL."""
        self._run("delete", hold_key(court_id, slot_date, start_time))

    def get_holds_for_venue(self, venue_id: int, target_date: str) -> List[dict]:
        return self._run("list_for_venue", int(venue_id), str(target_date))

    def is_slot_held_by_other(self, court_id: int, slot_date: str, start_time: str, user_id: int) -> bool:
        payload = self._run("get", hold_key(court_id, slot_date, start_time))
        return payload is not None and payload["user_id"] != user_id

    def clear_memory(self) -> None:
        """Dùng cho kiểm thử."""
        self._memory.clear()


# Global singleton
slot_lock_manager = SlotLockManager()
