from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class AddisPayWithdrawalRequest(BaseModel):
    """
    Schema for initiating a withdrawal request.
    This corresponds to the AddisPayWithdrawlRequestSchema.
    """
    cancel_url: str
    success_url: str
    error_url: str
    order_reason: str
    currency: str = "ETB"
    customer_name: str
    phone_number: str
    nonce: str
    payment_method: str = "telebirr"
    total_amount: str
    tx_ref: str
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True
        str_strip_whitespace = True
        json_schema_extra = {
            "example": {
                "cancel_url": "https://your-site.com/cancel",
                "success_url": "https://your-site.com/success",
                "error_url": "https://your-site.com/error",
                "order_reason": "Payment for services",
                "customer_name": "John Doe",
                "phone_number": "251911223344",
                "nonce": "unique_nonce_string_123",
                "total_amount": "100.00",
                "tx_ref": "your_unique_transaction_ref_456"
            }
        }