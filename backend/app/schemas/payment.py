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
    total_price: int
    deposit_amount: int
    paid_amount: int = 0
    amount_due: int                   # Phần tiền cọc còn phải chuyển
    remaining_amount: int             # Phần trả tại sân sau khi đã cọc
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
    total_price: int
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
    amount_in: int
    transaction_content: Optional[str] = None
    reference_number: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    booking: Optional[PaymentBookingSummary] = None

    model_config = ConfigDict(from_attributes=True)


class DailyRevenueResponse(BaseModel):
    """Doanh thu một ngày (giờ Việt Nam) của các cụm sân đang quản lý, lấy từ sổ giao dịch."""
    date: date
    venue_names: List[str]
    collected: int        # tiền cọc + thu tại sân, mọi hình thức
    cash: int             # phần thu bằng tiền mặt
    transfer: int         # phần thu bằng chuyển khoản
    refunded: int         # tiền đã hoàn cho khách
    net: int              # thực thu = collected - refunded
    plays_total: int      # lượt chơi trong ngày: đơn đã xác nhận, đang chơi hoặc đã xong
    plays_arrived: int    # trong đó khách đã nhận sân
    transactions: List[PaymentTransactionResponse]


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
    period_start: Optional[datetime] = None  # ca kéo dài từ đây (lần kết ca trước) tới closed_at
    closed_at: datetime
    closed_by_name: str
    opening_float: int
    counted_cash: int
    cash_collected: int
    transfer_collected: int
    refunded: int
    total_collected: int     # tiền mặt + chuyển khoản
    expected_cash: int       # tiền vốn + tiền mặt thu trong ca
    difference: int          # đếm được trừ phải có: dương là thừa, âm là thiếu
    note: Optional[str] = None


class ShiftSummaryResponse(BaseModel):
    """Ca đang chạy tại một cụm sân (các khoản chưa kết ca, giờ bắt đầu ca) và những lần kết ca gần đây."""
    venue_id: int
    venue_name: str
    business_date: date
    period_start: datetime                     # ca đang chạy bắt đầu từ lần kết ca trước (có thể là hôm trước)
    last_closed_at: Optional[datetime] = None  # lần kết ca gần nhất của cụm sân
    cash_collected: int
    transfer_collected: int
    refunded: int
    total_collected: int
    closings: List[ShiftClosingResponse]
