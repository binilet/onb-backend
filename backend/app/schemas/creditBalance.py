from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class CreditBalanceInDB(BaseModel):
    phone: str
    current_balance: float
    previous_balance: float
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    remark: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

