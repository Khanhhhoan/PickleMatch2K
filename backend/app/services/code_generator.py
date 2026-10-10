"""
Cấp mã đơn đặt sân (PK2K000123) và mã giao dịch (TX000123).

Trên PostgreSQL mã lấy từ sequence nên không trùng kể cả khi nhiều yêu cầu chạy đồng thời.
SQLite (chỉ dùng thử trên máy cá nhân) không có sequence nên lấy MAX(id) + 1.
"""
from sqlalchemy import func, text
from sqlalchemy.orm import Session

BOOKING_PREFIX = "PK2K"
TRANSACTION_PREFIX = "TX"
CODE_DIGITS = 6


def _next_number(db: Session, sequence: str, model) -> int:
    if db.get_bind().dialect.name == "postgresql":
        return int(db.execute(text(f"SELECT nextval('{sequence}')")).scalar())
    return int(db.query(func.coalesce(func.max(model.id), 0)).scalar()) + 1


def generate_next_booking_code(db: Session) -> str:
    from app.models.booking import Booking

    return f"{BOOKING_PREFIX}{_next_number(db, 'booking_code_seq', Booking):0{CODE_DIGITS}d}"


def generate_next_transaction_code(db: Session) -> str:
    from app.models.payment import PaymentTransaction

    return f"{TRANSACTION_PREFIX}{_next_number(db, 'transaction_code_seq', PaymentTransaction):0{CODE_DIGITS}d}"
