"""Kết ca tại quầy: đối chiếu tiền mặt đếm được với sổ giao dịch, rồi lưu lại thành một lần kết ca của cụm sân."""
import math
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.payment import PaymentKind, PaymentMethod, ShiftClosing
from app.models.user import User
from app.models.venue import Venue
from app.services import ledger
from app.utils.timeutils import now_utc, today_vn, vn_day_bounds_utc

MAX_AMOUNT = 1_000_000_000
RECENT_CLOSINGS = 10


@dataclass(frozen=True)
class Figures:
    """Các khoản sổ giao dịch đã ghi: tiền mặt thu, chuyển khoản nhận, tiền đã hoàn cho khách."""
    cash: float
    transfer: float
    refunded: float


def _day_figures(db: Session, venue_id: int, day: date) -> Figures:
    since, until = vn_day_bounds_utc(day)

    def total(kinds: tuple, method: Optional[str] = None) -> float:
        return ledger.sum_transactions(db, venue_ids=[venue_id], kinds=kinds, method=method, since=since, until=until)

    return Figures(
        cash=total(ledger.INCOMING_KINDS, PaymentMethod.CASH.value),
        transfer=total(ledger.INCOMING_KINDS, PaymentMethod.BANK_TRANSFER.value),
        refunded=total((PaymentKind.REFUND.value,)),
    )


def _closed_figures(db: Session, venue_id: int, day: date) -> Figures:
    row = (
        db.query(
            func.coalesce(func.sum(ShiftClosing.cash_collected), 0.0),
            func.coalesce(func.sum(ShiftClosing.transfer_collected), 0.0),
            func.coalesce(func.sum(ShiftClosing.refunded), 0.0),
        )
        .filter(ShiftClosing.venue_id == venue_id, ShiftClosing.business_date == day)
        .one()
    )
    return Figures(float(row[0]), float(row[1]), float(row[2]))


def open_figures(db: Session, venue_id: int, day: date) -> Figures:
    """
    Các khoản của ngày `day` chưa nằm trong lần kết ca nào: số của cả ngày trừ đi phần các lần kết ca trước đã ghi.
    Tính theo cách này thì một khoản ghi sổ sát lúc kết ca không bao giờ bị bỏ sót: nó thuộc về lần kết ca kế tiếp.
    """
    whole_day, closed = _day_figures(db, venue_id, day), _closed_figures(db, venue_id, day)
    return Figures(whole_day.cash - closed.cash, whole_day.transfer - closed.transfer, whole_day.refunded - closed.refunded)


def _whole_amount(value: float, label: str) -> float:
    if not math.isfinite(value) or value < 0 or value != int(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} phải là số nguyên, không âm.")
    if value > MAX_AMOUNT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} vượt quá mức cho phép.")
    return float(value)


def close_shift(db: Session, venue: Venue, actor: User, *, opening_float: float, counted_cash: float,
                note: Optional[str] = None) -> ShiftClosing:
    """Lưu một lần kết ca của hôm nay. Các khoản thu, hoàn lấy từ sổ giao dịch, không nhận từ người dùng."""
    opening_float = _whole_amount(opening_float, "Tiền vốn đầu ca")
    counted_cash = _whole_amount(counted_cash, "Tiền mặt đếm được")

    # Khóa dòng cụm sân để hai lần kết ca gửi cùng lúc không cùng tính một khoản
    db.query(Venue.id).filter(Venue.id == venue.id).with_for_update().one()
    day = today_vn()
    figures = open_figures(db, venue.id, day)
    closing = ShiftClosing(
        venue_id=venue.id,
        business_date=day,
        closed_by_id=actor.id,
        closed_at=now_utc(),
        opening_float=opening_float,
        counted_cash=counted_cash,
        cash_collected=figures.cash,
        transfer_collected=figures.transfer,
        refunded=figures.refunded,
        note=(note or "").strip() or None,
    )
    db.add(closing)
    db.commit()
    db.refresh(closing)
    return closing


def recent_closings(db: Session, venue_id: int, limit: int = RECENT_CLOSINGS) -> List[ShiftClosing]:
    return (
        db.query(ShiftClosing)
        .options(joinedload(ShiftClosing.closed_by))
        .filter(ShiftClosing.venue_id == venue_id)
        .order_by(ShiftClosing.closed_at.desc(), ShiftClosing.id.desc())
        .limit(limit)
        .all()
    )


def _display_name(user: Optional[User]) -> str:
    if user is None:
        return ""
    profile = user.staff_profile or user.owner_profile
    return (profile.full_name if profile and profile.full_name else None) or user.email.split("@")[0]


def describe(closing: ShiftClosing) -> dict:
    """Một lần kết ca kèm các số suy ra: tổng thu, tiền mặt phải có trong két và chênh lệch so với số đếm được."""
    expected_cash = closing.opening_float + closing.cash_collected
    return {
        "id": closing.id,
        "venue_id": closing.venue_id,
        "business_date": closing.business_date,
        "closed_at": closing.closed_at,
        "closed_by_name": _display_name(closing.closed_by),
        "opening_float": closing.opening_float,
        "counted_cash": closing.counted_cash,
        "cash_collected": closing.cash_collected,
        "transfer_collected": closing.transfer_collected,
        "refunded": closing.refunded,
        "total_collected": closing.cash_collected + closing.transfer_collected,
        "expected_cash": expected_cash,
        "difference": closing.counted_cash - expected_cash,
        "note": closing.note,
    }


def summary(db: Session, venue: Venue) -> dict:
    """Các khoản của hôm nay chưa kết ca tại cụm sân, kèm những lần kết ca gần đây (mới nhất trước)."""
    day = today_vn()
    figures = open_figures(db, venue.id, day)
    closings = recent_closings(db, venue.id)
    last_today = next((c for c in closings if c.business_date == day), None)
    return {
        "venue_id": venue.id,
        "venue_name": venue.name,
        "business_date": day,
        "last_closed_at": last_today.closed_at if last_today else None,
        "cash_collected": figures.cash,
        "transfer_collected": figures.transfer,
        "refunded": figures.refunded,
        "total_collected": figures.cash + figures.transfer,
        "closings": [describe(c) for c in closings],
    }
