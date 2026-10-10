"""Sổ giao dịch: mọi khoản tiền vào/ra của một đơn đặt đều được ghi thành PaymentTransaction."""
import json
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.booking import Booking, BookingDetail
from app.models.payment import PaymentKind, PaymentMethod, PaymentTransaction
from app.models.venue import Court
from app.services.code_generator import generate_next_transaction_code

INCOMING_KINDS = (PaymentKind.DEPOSIT.value, PaymentKind.BALANCE.value)


def record_transaction(
    db: Session,
    booking: Booking,
    *,
    amount: float,
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
        amount_in=float(amount),
        transaction_content=content,
        reference_number=reference_number or None,
        status="SUCCESS",
        raw_payload=json.dumps(raw_payload, default=str) if raw_payload is not None else None,
        created_by_id=created_by_id,
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
) -> float:
    """Tổng tiền các giao dịch thành công thuộc phạm vi cụm sân, lọc theo loại/phương thức/khoảng thời gian."""
    booking_ids = venue_booking_ids_subquery(db, venue_ids)
    query = db.query(func.coalesce(func.sum(PaymentTransaction.amount_in), 0.0)).filter(
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
    return float(query.scalar() or 0.0)
