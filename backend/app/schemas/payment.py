from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
