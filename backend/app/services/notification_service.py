"""
Thông báo trong ứng dụng.

notify() ghi thông báo trong CÙNG giao dịch với thay đổi trạng thái gây ra nó: giao dịch bị hủy thì thông báo cũng không
có, giao dịch thành công thì thông báo chắc chắn đã lưu. Mỗi sự kiện có event_key; cùng sự kiện, cùng người chỉ ghi một
lần (ràng buộc unique + ON CONFLICT DO NOTHING), nên tác vụ nền chạy lại hay hai tiến trình cùng xử lý không tạo
thông báo trùng. Sau khi giao dịch commit, những người vừa có thông báo mới nhận tín hiệu qua kênh WebSocket riêng để
chuông cập nhật ngay; mất tín hiệu này cũng không mất thông báo.
"""
from typing import Iterable, List, Optional

from sqlalchemy import event
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.websocket_manager import dispatch, manager
from app.models.match import Match, ParticipantStatus
from app.models.notification import Notification
from app.utils.timeutils import now_utc

MATCHES_LINK = "/matches?tab=my_matches"
_PENDING_PUSH = "pending_notification_push"


def notify(db: Session, user_ids: Iterable[Optional[int]], *, kind: str, title: str, body: str, event_key: str,
           link: Optional[str] = None) -> List[int]:
    """Ghi một thông báo cho từng người (bỏ qua người đã có thông báo cùng event_key). Trả về id người vừa được báo."""
    targets = sorted({uid for uid in user_ids if uid})
    if not targets:
        return []
    rows = [
        {"user_id": uid, "kind": kind, "title": title[:160], "body": body[:500], "link": link,
         "event_key": event_key[:120], "created_at": now_utc()}
        for uid in targets
    ]
    if db.get_bind().dialect.name == "postgresql":
        statement = (
            pg_insert(Notification).values(rows)
            .on_conflict_do_nothing(constraint="uq_notifications_user_event")
            .returning(Notification.user_id)
        )
        created = [row[0] for row in db.execute(statement)]
    else:  # SQLite chỉ dùng thử
        existing = {
            uid for (uid,) in db.query(Notification.user_id)
            .filter(Notification.user_id.in_(targets), Notification.event_key == event_key[:120])
        }
        created = [row["user_id"] for row in rows if row["user_id"] not in existing]
        db.add_all(Notification(**row) for row in rows if row["user_id"] in created)
        db.flush()
    db.info.setdefault(_PENDING_PUSH, set()).update(created)
    return created


@event.listens_for(Session, "after_commit")
def _push_after_commit(session: Session) -> None:
    for user_id in sorted(session.info.pop(_PENDING_PUSH, set())):
        dispatch(manager.send_to_user(user_id, {"type": "NOTIFICATION_CREATED"}))


@event.listens_for(Session, "after_rollback")
def _forget_after_rollback(session: Session) -> None:
    session.info.pop(_PENDING_PUSH, None)


def _when(match: Match) -> str:
    return f"{match.start_time:%H:%M}-{match.end_time:%H:%M} ngày {match.date:%d/%m/%Y}"


def _room(match: Match) -> str:
    return f"phòng tại {match.venue_name or 'cụm sân'} lúc {_when(match)}"


def notify_match_cancelled(db: Session, match: Match, reason: str, *, exclude_user_id: Optional[int] = None) -> List[int]:
    """Phòng đấu vừa bị hủy: báo cho chủ phòng, mọi thành viên và người đang chờ duyệt (trừ người tự tay hủy)."""
    people = {match.creator_id} | {
        p.user_id for p in match.participants
        if p.status in (ParticipantStatus.ACCEPTED.value, ParticipantStatus.PENDING.value)
    }
    people.discard(exclude_user_id)
    return notify(
        db, people, kind="MATCH_CANCELLED", title="Phòng đấu đã bị hủy",
        body=f"Rất tiếc, {_room(match)} đã bị hủy: {reason}.", link=MATCHES_LINK,
        event_key=f"match:{match.id}:cancelled",
    )


def notify_join_request(db: Session, match: Match, requester_name: str, requester_id: int) -> List[int]:
    return notify(
        db, [match.creator_id], kind="MATCH_REQUEST", title="Có người xin vào phòng của bạn",
        body=f"{requester_name} xin tham gia {_room(match)}. Mở phòng để chấp nhận hoặc từ chối.",
        link=MATCHES_LINK, event_key=f"match:{match.id}:request:{requester_id}",
    )


def notify_join_decision(db: Session, match: Match, user_id: int, accepted: bool) -> List[int]:
    if accepted:
        title, body = "Bạn đã được nhận vào phòng", f"Chủ phòng đã nhận bạn vào {_room(match)}. Số điện thoại của các thành viên đã hiện trong phòng."
    else:
        title, body = "Yêu cầu tham gia bị từ chối", f"Chủ phòng đã từ chối yêu cầu tham gia {_room(match)}."
    return notify(
        db, [user_id], kind="MATCH_ACCEPTED" if accepted else "MATCH_REJECTED", title=title, body=body,
        link=MATCHES_LINK, event_key=f"match:{match.id}:decision:{user_id}",
    )
