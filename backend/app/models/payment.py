import enum

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, text
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
    amount_in = Column(Float, nullable=False, default=0.0)
    transaction_content = Column(String, nullable=True)
    reference_number = Column(String, nullable=True, index=True)
    status = Column(String, default="SUCCESS", nullable=False)  # SUCCESS, FAILED
    raw_payload = Column(String, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Nhân viên ghi nhận (thu tiền mặt, hoàn tiền)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    booking = relationship("Booking")
