"""
Kết ca tại quầy: đối chiếu tiền mặt đếm được với sổ giao dịch, rồi lưu lại thành một lần kết ca của cụm sân.

Một ca không gắn với ngày lịch. Ca kéo dài từ lần kết ca trước của cụm sân tới lúc kết ca này, nên ca 20:00 tới
00:15 hôm sau vẫn là một ca. Mỗi lần kết ca nhận đúng những giao dịch trong sổ chưa thuộc ca nào, rồi gắn chúng vào
mình (PaymentTransaction.shift_closing_id):
- không giao dịch nào bị tính vào hai ca;
- khoản ghi sổ muộn (giao dịch ghi xong sau khi đã kết ca) không bị bỏ sót: nó thuộc về lần kết ca kế tiếp;
- quên kết ca một hôm thì lần kết ca sau nhận luôn phần còn treo, thấy được qua giờ bắt đầu ca.
Báo cáo doanh thu theo ngày vẫn tính theo ngày lịch (ledger.daily_net_revenue), độc lập với các ca.
"""
import math
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.payment import PaymentKind, PaymentMethod, PaymentTransaction, ShiftClosing
from app.models.user import User
from app.models.venue import Venue
from app.core.money import vnd
from app.services import ledger
from app.utils.timeutils import as_utc, now_utc, today_vn, vn_day_bounds_utc

MAX_AMOUNT = 1_000_000_000
RECENT_CLOSINGS = 10


@dataclass(frozen=True)
class Figures:
    """Các khoản sổ giao dịch đã ghi: tiền mặt thu, chuyển khoản nhận, tiền đã hoàn cho khách."""
    cash: int
    transfer: int
    refunded: int


def ledger_start(db: Session, venue_id: int) -> datetime:
    """
    Từ thời điểm này giao dịch của cụm sân mới thuộc sổ kết ca: 0 giờ (giờ Việt Nam) của ngày có lần kết ca đầu tiên,
    hoặc 0 giờ hôm nay nếu cụm sân chưa kết ca lần nào. Giao dịch trước đó là lịch sử, không thuộc ca nào.
    """
    first = db.query(func.min(ShiftClosing.business_date)).filter(ShiftClosing.venue_id == venue_id).scalar()
    return vn_day_bounds_utc(first or today_vn())[0]


def _open_transactions_query(db: Session, venue_id: int):
    booking_ids = ledger.venue_booking_ids_subquery(db, [venue_id])
    return db.query(PaymentTransaction).filter(
        PaymentTransaction.status == "SUCCESS",
        PaymentTransaction.shift_closing_id.is_(None),
        PaymentTransaction.created_at >= ledger_start(db, venue_id),
        PaymentTransaction.booking_id.in_(db.query(booking_ids.c.booking_id)),
    )


def _figures(transactions: List[PaymentTransaction]) -> Figures:
    def total(kinds: tuple, method: Optional[str] = None) -> int:
        return sum(vnd(t.amount_in) for t in transactions if t.kind in kinds and (method is None or t.method == method))

    return Figures(
        cash=total(ledger.INCOMING_KINDS, PaymentMethod.CASH.value),
        transfer=total(ledger.INCOMING_KINDS, PaymentMethod.BANK_TRANSFER.value),
        refunded=total((PaymentKind.REFUND.value,)),
    )


def open_figures(db: Session, venue_id: int) -> Figures:
    """Các khoản chưa thuộc lần kết ca nào của cụm sân: chính là số của ca đang chạy."""
    return _figures(_open_transactions_query(db, venue_id).all())


def current_shift_start(db: Session, venue_id: int) -> datetime:
    """Ca đang chạy bắt đầu từ lần kết ca gần nhất của cụm sân (hoặc từ lúc sổ kết ca bắt đầu)."""
    last = db.query(func.max(ShiftClosing.closed_at)).filter(ShiftClosing.venue_id == venue_id).scalar()
    return as_utc(last) if last is not None else ledger_start(db, venue_id)


def _whole_amount(value: float, label: str) -> int:
    if not math.isfinite(value) or value < 0 or value != int(value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} phải là số nguyên, không âm.")
    if value > MAX_AMOUNT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{label} vượt quá mức cho phép.")
    return int(value)


def close_shift(db: Session, venue: Venue, actor: User, *, opening_float: float, counted_cash: float,
                note: Optional[str] = None) -> ShiftClosing:
    """
    Kết ca đang chạy: nhận mọi giao dịch chưa thuộc ca nào của cụm sân và gắn chúng vào lần kết ca này.
    Các khoản thu, hoàn lấy từ sổ giao dịch, không nhận từ người dùng.
    """
    opening_float = _whole_amount(opening_float, "Tiền vốn đầu ca")
    counted_cash = _whole_amount(counted_cash, "Tiền mặt đếm được")

    # Khóa dòng cụm sân để hai lần kết ca gửi cùng lúc diễn ra lần lượt: lần sau thấy các giao dịch lần trước đã gắn
    db.query(Venue.id).filter(Venue.id == venue.id).with_for_update().one()
    period_start = current_shift_start(db, venue.id)
    transactions = _open_transactions_query(db, venue.id).with_for_update().all()
    figures = _figures(transactions)
    closed_at = now_utc()
    closing = ShiftClosing(
        venue_id=venue.id,
        business_date=today_vn(),
        closed_by_id=actor.id,
        period_start=min(period_start, closed_at),
        closed_at=closed_at,
        opening_float=opening_float,
        counted_cash=counted_cash,
        cash_collected=figures.cash,
        transfer_collected=figures.transfer,
        refunded=figures.refunded,
        note=(note or "").strip() or None,
    )
    db.add(closing)
    db.flush()
    for transaction in transactions:
        transaction.shift_closing_id = closing.id
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
        "period_start": closing.period_start,
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
    """Ca đang chạy của cụm sân (các khoản chưa kết ca, giờ bắt đầu ca), kèm những lần kết ca gần đây (mới nhất trước)."""
    figures = open_figures(db, venue.id)
    closings = recent_closings(db, venue.id)
    return {
        "venue_id": venue.id,
        "venue_name": venue.name,
        "business_date": today_vn(),
        "period_start": current_shift_start(db, venue.id),
        "last_closed_at": closings[0].closed_at if closings else None,
        "cash_collected": figures.cash,
        "transfer_collected": figures.transfer,
        "refunded": figures.refunded,
        "total_collected": figures.cash + figures.transfer,
        "closings": [describe(c) for c in closings],
    }
