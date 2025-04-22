from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SantimDepositStatusInDB(BaseModel):
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
    successRedirectUrl: str
    failureRedirectUrl: str
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