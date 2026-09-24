from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


PlayerRoomWalletReason = Literal["CASHIER_TOPUP", "DEPOSIT", "GAME_STAKE", "GAME_WINNINGS", "REFUND"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PlayerRoomWallet(BaseModel):
    playerPhone: str
    shopId: str
    branchId: Optional[str] = None
    currentBalance: Decimal = Field(default=Decimal("0"))
    isWithdrawable: bool
    updatedAt: datetime = Field(default_factory=utc_now)


class PlayerRoomWalletLedger(BaseModel):
    ledger_id: str = Field(default_factory=lambda: str(uuid4()))
    playerPhone: str
    shopId: str
    branchId: Optional[str] = None
    amount: Decimal
    reason: PlayerRoomWalletReason
    toppedUpByPhone: Optional[str] = None
    idempotencyKey: str = Field(min_length=1)
    createdAt: datetime = Field(default_factory=utc_now)


class PlayerRoomTopUpRequest(BaseModel):
    playerPhone: str
    shopId: str
    branchId: Optional[str] = None
    amount: Decimal = Field(gt=0)
    idempotencyKey: str = Field(min_length=1)
