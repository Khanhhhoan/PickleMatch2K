"""Sổ giao dịch: mọi khoản tiền vào/ra của một đơn đặt đều được ghi thành PaymentTransaction."""
import json
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.core.money import vnd
from app.models.booking import Booking, BookingDetail
from app.models.payment import PaymentKind, PaymentMethod, PaymentTransaction
from app.models.venue import Court
from app.services.code_generator import generate_next_transaction_code
from app.utils.timeutils import VN_TZ_NAME, now_utc

INCOMING_KINDS = (PaymentKind.DEPOSIT.value, PaymentKind.BALANCE.value)


def record_transaction(
    db: Session,
    booking: Booking,
    *,
    amount: int,
    kind: str,
    method: str = PaymentMethod.BANK_TRANSFER.value,
    gateway: str = "SePay_VietQR",
    reference_number: Optional[str] = None,
    content: Optional[str] = None,
    account_number: Optional[str] = None,
    raw_payload: Optional[dict] = None,
    created_by_id: Optional[int] = None,
) -> PaymentTransaction:
    txn = PaymentTransaction(
        transaction_code=generate_next_transaction_code(db),
        booking_id=booking.id,
        gateway=gateway,
        method=method,
        kind=kind,
        account_number=account_number,
        amount_in=vnd(amount),
        transaction_content=content,
        reference_number=reference_number or None,
        status="SUCCESS",
        raw_payload=json.dumps(raw_payload, default=str) if raw_payload is not None else None,
        created_by_id=created_by_id,
        # Thời điểm ghi sổ lấy theo đồng hồ nghiệp vụ của ứng dụng (cùng nguồn với giờ kết ca), không theo đồng hồ CSDL
        created_at=now_utc(),
    )
    db.add(txn)
    db.flush()
    return txn


def find_by_reference(db: Session, reference_number: Optional[str]) -> Optional[PaymentTransaction]:
    if not reference_number:
        return None
    return db.query(PaymentTransaction).filter(PaymentTransaction.reference_number == reference_number).first()


def venue_booking_ids_subquery(db: Session, venue_ids: Optional[List[int]]):
    """Subquery id các đơn có ít nhất một khung giờ thuộc các cụm sân cho trước (None = mọi cụm sân)."""
    query = db.query(BookingDetail.booking_id).join(Court, Court.id == BookingDetail.court_id)
    if venue_ids is not None:
        query = query.filter(Court.venue_id.in_(venue_ids))
    return query.distinct().subquery()


def sum_transactions(
    db: Session,
    *,
    venue_ids: Optional[List[int]],
    kinds: tuple,
    method: Optional[str] = None,
    since=None,
    until=None,
) -> int:
    """Tổng tiền các giao dịch thành công thuộc phạm vi cụm sân, lọc theo loại/phương thức/khoảng thời gian."""
    booking_ids = venue_booking_ids_subquery(db, venue_ids)
    query = db.query(func.coalesce(func.sum(PaymentTransaction.amount_in), 0)).filter(
        PaymentTransaction.status == "SUCCESS",
        PaymentTransaction.kind.in_(kinds),
        PaymentTransaction.booking_id.in_(db.query(booking_ids.c.booking_id)),
    )
    if method:
        query = query.filter(PaymentTransaction.method == method)
    if since is not None:
        query = query.filter(PaymentTransaction.created_at >= since)
    if until is not None:
        query = query.filter(PaymentTransaction.created_at < until)
    return vnd(query.scalar())


def transactions_between(db: Session, *, venue_ids: Optional[List[int]], since, until) -> List[PaymentTransaction]:
    """Các giao dịch thành công thuộc phạm vi cụm sân trong khoảng [since, until), mới trước cũ sau."""
    booking_ids = venue_booking_ids_subquery(db, venue_ids)
    return (
        db.query(PaymentTransaction)
        .options(joinedload(PaymentTransaction.booking))
        .filter(
            PaymentTransaction.status == "SUCCESS",
            PaymentTransaction.booking_id.in_(db.query(booking_ids.c.booking_id)),
            PaymentTransaction.created_at >= since,
            PaymentTransaction.created_at < until,
        )
        .order_by(PaymentTransaction.created_at.desc(), PaymentTransaction.id.desc())
        .all()
    )


def vn_day(column):
    """Biểu thức SQL: ngày theo giờ Việt Nam của một cột thời điểm (cột lưu UTC), dùng để gom nhóm theo ngày."""
    return func.date(func.timezone(VN_TZ_NAME, column))


def _signed_amount():
    """Biểu thức SQL: số tiền của giao dịch, khoản hoàn mang dấu âm."""
    return case(
        (PaymentTransaction.kind == PaymentKind.REFUND.value, -PaymentTransaction.amount_in),
        else_=PaymentTransaction.amount_in,
    )


def daily_net_revenue(db: Session, *, venue_ids: Optional[List[int]]) -> Dict[date, int]:
    """Thực thu từng ngày (khoản thu trừ khoản hoàn) của các giao dịch thành công thuộc phạm vi cụm sân."""
    booking_ids = venue_booking_ids_subquery(db, venue_ids)
    day = vn_day(PaymentTransaction.created_at)
    rows = (
        db.query(day, func.sum(_signed_amount()))
        .filter(
            PaymentTransaction.status == "SUCCESS",
            PaymentTransaction.created_at.isnot(None),
            PaymentTransaction.booking_id.in_(db.query(booking_ids.c.booking_id)),
        )
        .group_by(day)
        .all()
    )
    return {row[0]: vnd(row[1]) for row in rows}


def booking_venue_subquery(db: Session):
    """Subquery (booking_id, venue_id): cụm sân của từng đơn.

    Một đơn chỉ gồm các sân của cùng một cụm sân (kể cả sau khi dời lịch). Nếu dữ liệu cũ có đơn trải trên nhiều cụm
    sân thì lấy cụm sân có id nhỏ nhất, để khi tách theo cụm sân không đơn nào bị tính hai lần.
    """
    return (
        db.query(BookingDetail.booking_id.label("booking_id"), func.min(Court.venue_id).label("venue_id"))
        .join(Court, Court.id == BookingDetail.court_id)
        .group_by(BookingDetail.booking_id)
        .subquery()
    )


def daily_net_revenue_by_venue(db: Session, *, venue_ids: List[int]) -> Dict[int, Dict[date, int]]:
    """Như daily_net_revenue nhưng tách theo cụm sân của đơn: {venue_id: {ngày: thực thu}}."""
    booking_venue = booking_venue_subquery(db)
    day = vn_day(PaymentTransaction.created_at)
    rows = (
        db.query(booking_venue.c.venue_id, day, func.sum(_signed_amount()))
        .select_from(PaymentTransaction)
        .join(booking_venue, booking_venue.c.booking_id == PaymentTransaction.booking_id)
        .filter(
            PaymentTransaction.status == "SUCCESS",
            PaymentTransaction.created_at.isnot(None),
            booking_venue.c.venue_id.in_(venue_ids or [0]),
        )
        .group_by(booking_venue.c.venue_id, day)
        .all()
    )
    result: Dict[int, Dict[date, int]] = {}
    for venue_id, day_value, amount in rows:
        result.setdefault(venue_id, {})[day_value] = vnd(amount)
    return result
