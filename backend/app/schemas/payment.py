from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SepayWebhookPayload(BaseModel):
    id: Optional[int] = None
    gateway: Optional[str] = None
    transactionDate: Optional[str] = None
    accountNumber: Optional[str] = None
    subAccount: Optional[str] = None
    amountIn: Optional[float] = 0.0
    amountOut: Optional[float] = 0.0
    accumulated: Optional[float] = 0.0
    code: Optional[str] = None
    transactionContent: Optional[str] = None
    referenceNumber: Optional[str] = None
    body: Optional[str] = None
    # Official SePay field names
    content: Optional[str] = None
    transferType: Optional[str] = None
    transferAmount: Optional[float] = 0.0
    referenceCode: Optional[str] = None
    description: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class CheckoutResponse(BaseModel):
    booking_id: int
    booking_code: Optional[str] = None
    status: str
    total_price: float
    deposit_amount: float
    paid_amount: float = 0.0
    amount_due: float                 # Phần tiền cọc còn phải chuyển
    remaining_amount: float           # Phần trả tại sân sau khi đã cọc
    deposit_percentage: int = 50
    payment_status: str
    venue_name: str
    bank_name: str
    bank_code: str
    bank_account_number: str
    account_holder_name: str
    transfer_content: str
    qr_code_url: str
    expires_in_seconds: int = 0
    simulator_enabled: bool = False


class PaymentConfigResponse(BaseModel):
    simulator_enabled: bool
    unified_account_mode: bool


class PaymentBookingSummary(BaseModel):
    id: int
    booking_code: Optional[str] = None
    total_price: float
    payment_status: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PaymentTransactionResponse(BaseModel):
    id: int
    transaction_code: Optional[str] = None
    booking_id: int
    gateway: str
    method: Optional[str] = None
    kind: Optional[str] = None
    amount_in: float
    transaction_content: Optional[str] = None
    reference_number: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    booking: Optional[PaymentBookingSummary] = None

    model_config = ConfigDict(from_attributes=True)


class ShiftClosingCreate(BaseModel):
    """Kết ca: người dùng chỉ nhập tiền vốn và tiền mặt đếm được; các khoản thu, hoàn do máy chủ lấy từ sổ giao dịch."""
    venue_id: Optional[int] = None  # bỏ trống = cụm sân đầu tiên người dùng quản lý
    opening_float: float
    counted_cash: float
    note: Optional[str] = Field(default=None, max_length=300)


class ShiftClosingResponse(BaseModel):
    id: int
    venue_id: int
    business_date: date
    closed_at: datetime
    closed_by_name: str
    opening_float: float
    counted_cash: float
    cash_collected: float
    transfer_collected: float
    refunded: float
    total_collected: float   # tiền mặt + chuyển khoản
    expected_cash: float     # tiền vốn + tiền mặt thu trong ca
    difference: float        # đếm được trừ phải có: dương là thừa, âm là thiếu
    note: Optional[str] = None


class ShiftSummaryResponse(BaseModel):
    """Phần của hôm nay chưa kết ca tại một cụm sân và những lần kết ca gần đây."""
    venue_id: int
    venue_name: str
    business_date: date
    last_closed_at: Optional[datetime] = None  # lần kết ca gần nhất trong hôm nay
    cash_collected: float
    transfer_collected: float
    refunded: float
    total_collected: float
    closings: List[ShiftClosingResponse]
