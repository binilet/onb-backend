from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ManualDepositRequestBase(BaseModel):
    phone: str
    amount: float
    receiptMessage: str
    trxId: Optional[str] = None
    userName: Optional[str] = None
    processed: Optional[bool] = False
    isVerified: Optional[bool] = False
    processingMsg: Optional[str] = None
    status:Optional[str] = None

class ManualDepositRequest(ManualDepositRequestBase):
    id: str = Field(..., alias="_id")
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True
        validate_by_name = True
