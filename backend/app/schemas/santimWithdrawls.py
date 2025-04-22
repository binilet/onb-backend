from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SantimWithdrawlRequestInDB(BaseModel):
    trxId: str
    phone: str
    amount: float
    paymentMethod: str
    status: str
    type: Optional[str] = None
    createdAt: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class SantimWithdrawlStatusInDB(BaseModel):
    txnId: str
    created_at: datetime
    updated_at: datetime
    thirdPartyId: str
    merId: str
    merName: str
    address: str
    amount: str
    currency: str
    reason: str
    msisdn: str
    accountNumber: str
    paymentVia: str
    refId: str
    message: str
    Status: str
    receiverWalletID: str
    is_header_valid: bool
    has_system_error: bool
    hagereMessage: str

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }