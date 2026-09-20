from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


LedgerReason = Literal[
    "SYSTEM_TO_AGENT_GRANT",
    "SYSTEM_TO_ADMIN_GRANT",
    "SYSTEM_TO_CASHIER_GRANT",
    "AGENT_TO_ADMIN_TRANSFER",
    "ADMIN_TO_CASHIER_TRANSFER",
    "PLAYER_TOPUP",
    "GAME_STAKE",
    "GAME_WINNINGS",
    "REFUND",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ShopBalance(BaseModel):
    phone: str
    currentBalance: Decimal = Field(default=Decimal("0"))
    updatedAt: datetime = Field(default_factory=utc_now)


class ShopBalanceLedger(BaseModel):
    ledger_id: str = Field(default_factory=lambda: str(uuid4()))
    fromPhone: Optional[str] = None
    toPhone: str
    amountPoints: Decimal = Field(gt=0)
    etbAmount: Optional[Decimal] = None
    systemCutPercentApplied: Optional[Decimal] = None
    reason: LedgerReason
    idempotencyKey: str = Field(min_length=1)
    createdAt: datetime = Field(default_factory=utc_now)


class BalanceTransferRequest(BaseModel):
    toPhone: str
    idempotencyKey: str = Field(min_length=1)
    shopId: Optional[str] = None
    etbAmount: Optional[Decimal] = Field(default=None, gt=0)
    amountPoints: Optional[Decimal] = Field(default=None, gt=0)
