from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class OrderDetail(BaseModel):
    amount: float
    description: str


class AddisPayDepositRequestBase(BaseModel):
    uuid: str
    redirect_url: str
    cancel_url: str
    success_url: str
    error_url: str
    order_reason: str
    currency: str
    email: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    nonce: str
    order_detail: OrderDetail
    phone_number: str
    session_expired: str  # Could be `datetime` if format is consistent
    total_amount: str     # Consider converting to float if needed
    tx_ref: str
    status: str = "requested"


class AddisPayDepositRequest(AddisPayDepositRequestBase):
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
