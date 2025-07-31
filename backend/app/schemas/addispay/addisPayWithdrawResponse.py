from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime

class AddisPayWithdrawalResponse(BaseModel):
    """
    Schema for the API's response after a withdrawal request.
    This corresponds to the AddisPayWithdrawalResponseSchema.
    """
    status_code: int
    requestedAmount: str
    requestingUser: str
    trxId: str
    message: Optional[str] = None
    details: Optional[str] = None
    data: Optional[str] = None
    success: Optional[bool] = None
    
    # Mongoose's `timestamps: true` is represented by these fields
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        str_strip_whitespace = True