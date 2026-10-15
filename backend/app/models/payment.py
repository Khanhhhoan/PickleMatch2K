import enum

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class PaymentMethod(str, enum.Enum):
    BANK_TRANSFER = "BANK_TRANSFER"  # Chuyển khoản (SePay VietQR hoặc chuyển khoản tại quầy)
    CASH = "CASH"                    # Tiền mặt thu tại quầy


class PaymentKind(str, enum.Enum):
    DEPOSIT = "DEPOSIT"  # Tiền cọc / thanh toán trước khi đến sân
    BALANCE = "BALANCE"  # Phần còn lại thu khi khách nhận sân
    REFUND = "REFUND"    # Tiền hoàn lại cho khách (amount_in là số tiền đã hoàn)


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        # Mỗi mã tham chiếu ngân hàng chỉ được ghi nhận một lần (chống xử lý trùng webhook)
        Index(
            "uq_payment_transactions_reference", "reference_number", unique=True,
            postgresql_where=text("reference_number IS NOT NULL AND reference_number <> ''"),
            sqlite_where=text("reference_number IS NOT NULL AND reference_number <> ''"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    transaction_code = Column(String(32), unique=True, index=True, nullable=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    gateway = Column(String, default="SePay_VietQR", nullable=False)
    method = Column(String, default=PaymentMethod.BANK_TRANSFER.value, server_default=PaymentMethod.BANK_TRANSFER.value, nullable=False)
    kind = Column(String, default=PaymentKind.DEPOSIT.value, server_default=PaymentKind.DEPOSIT.value, nullable=False)
    transaction_date = Column(DateTime(timezone=True), server_default=func.now())
    account_number = Column(String, nullable=True)
    amount_in = Column(BigInteger, nullable=False, default=0)  # số nguyên đồng
    transaction_content = Column(String, nullable=True)
    reference_number = Column(String, nullable=True, index=True)
    status = Column(String, default="SUCCESS", nullable=False)  # SUCCESS, FAILED
    raw_payload = Column(String, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nhân viên ghi nhận (thu tiền mặt, hoàn tiền)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Lần kết ca đã tính khoản này (NULL = chưa kết ca). Mỗi giao dịch chỉ thuộc một ca, nên không bị tính hai lần.
    shift_closing_id = Column(Integer, ForeignKey("shift_closings.id", ondelete="SET NULL"), nullable=True, index=True)

    booking = relationship("Booking")


class ShiftClosing(Base):
    """
    Một lần kết ca tại quầy của một cụm sân. Người kết ca nhập tiền vốn đầu ca và tiền mặt đếm được; các khoản
    thu, hoàn là những giao dịch trong sổ chưa thuộc lần kết ca nào, và được gắn vào lần kết ca này
    (PaymentTransaction.shift_closing_id). Ca không gắn với ngày lịch: ca 20:00 - 00:15 hôm sau vẫn là một ca, và
    khoản ghi sổ muộn (sau khi đã kết ca) thuộc về lần kết ca kế tiếp, không bị bỏ sót hay tính hai lần.
    """
    __tablename__ = "shift_closings"
    __table_args__ = (Index("ix_shift_closings_venue_date", "venue_id", "business_date"),)

    id = Column(Integer, primary_key=True, index=True)
    venue_id = Column(Integer, ForeignKey("venues.id", ondelete="CASCADE"), nullable=False)
    business_date = Column(Date, nullable=False)                       # ngày kết ca theo giờ Việt Nam
    closed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Ca kéo dài từ period_start (lần kết ca trước của cụm sân) tới closed_at, kể cả khi qua nửa đêm
    period_start = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    opening_float = Column(BigInteger, nullable=False)                 # tiền vốn có sẵn trong két đầu ca
    counted_cash = Column(BigInteger, nullable=False)                  # tiền mặt đếm được khi kết ca
    cash_collected = Column(BigInteger, nullable=False)                # tiền mặt thu trong ca theo sổ giao dịch
    transfer_collected = Column(BigInteger, nullable=False)            # chuyển khoản nhận trong ca theo sổ giao dịch
    refunded = Column(BigInteger, nullable=False, default=0, server_default="0")  # tiền đã hoàn cho khách trong ca
    note = Column(String(300), nullable=True)

    venue = relationship("Venue")
    closed_by = relationship("User")
