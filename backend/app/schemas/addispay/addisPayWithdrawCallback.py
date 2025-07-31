from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class CustomerData(BaseModel):
    merchant_id: str

class CallbackResourceData(BaseModel):
    id: str
    amount: float
    currency: str
    status: str
    payment_method: str
    customer: CustomerData

class AddisPayWithdrawalCallback(BaseModel):
    """
    Schema for handling the callback from AddisPay.
    This corresponds to the AddisPayWithdrawlCallbackSchema.
    """
    id: str
    event_type: str
    created_at: str  # Kept as string to match the ISO format from the callback
    resource_type: str
    resource_id: str
    data: CallbackResourceData
    signature: Optional[str] = None
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True
        str_strip_whitespace = True
