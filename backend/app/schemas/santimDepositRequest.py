from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SantimDepositRequestInDB(BaseModel):
    txnId: Optional[str] = None  # May not be available until callback
    amount: str
    reason: str
    phone: str
    returnedUrl: str
    refId: str
    createdAt: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()  # Convert datetime to ISO 8601 string
        }