from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Order(BaseModel):
    description: str


class AddisPayDepositCallbackBase(BaseModel):
    session_uuid: str
    addispay_transaction_id: str
    total_amount: float
    paymnet_reason: str  # Keeping original spelling
    payment_status: str
    order_id: str
    nonce: str
    order: Order
    status: str = "received"


class AddisPayDepositCallback(AddisPayDepositCallbackBase):
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
