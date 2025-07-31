# models/with_request.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class ManualWithRequestBase(BaseModel):
    trxid: str
    phone: str
    username: str
    amount: float
    approved: bool = False
    reference: Optional[str] = ""
    approvedBy: Optional[str] = ""
    void: bool = False
    note: Optional[str] = ""

class ManualWithRequest(ManualWithRequestBase):
    id: str = Field(..., alias="_id")
    createdAt: datetime
    updatedAt: datetime

    class Config:
        from_attributes = True
        validate_by_name  = True
