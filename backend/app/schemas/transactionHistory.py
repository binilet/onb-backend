from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class TransactionHistoryBase(BaseModel):
    phone: str = Field(..., regex=r'^\d{10,15}$', description="Phone number must be 10 to 15 digits")
    date: datetime = Field(default_factory=datetime.utcnow)
    game_id: Optional[str] = Field(default=None)
    transaction_ref: Optional[str] = Field(default=None)
    amount: float = Field(..., gt=0, description="Amount must be greater than 0")
    type: Literal["deposit", "withdrawal", "bet", "win", "transfer"]
    message: str = Field(..., max_length=200)
    isdebit: bool = True
    reference: Optional[str] = Field(default=None)
    remark: Optional[str] = Field(default="")


class TransactionHistoryCreate(TransactionHistoryBase):
    pass  # Use this when accepting input from users


class TransactionHistoryResponse(TransactionHistoryBase):
    id: str = Field(..., alias="_id")  # MongoDB will return _id
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
