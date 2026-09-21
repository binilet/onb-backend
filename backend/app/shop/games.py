from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


GameStatus = Literal["PENDING", "ACTIVE", "COMPLETE", "VOID"]
GameStartMode = Literal["TIMER", "MANUAL"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ShopGameCreate(BaseModel):
    shopId: str
    branchId: str
    pattern: Optional[str] = None
    dynamicPattern: Optional[str] = None
    betAmount: Decimal = Field(gt=0)
    totalWinning: Optional[Decimal] = Field(default=None, ge=0)
    totalCutPercent: Decimal = Field(default=Decimal("10"), ge=10)
    startMode: GameStartMode = "MANUAL"
    scheduledStartAt: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_existing_pattern_mechanism(self):
        if bool(self.pattern) == bool(self.dynamicPattern):
            raise ValueError("Select exactly one pattern: either static pattern or dynamic pattern")
        if self.startMode == "TIMER" and self.scheduledStartAt is None:
            raise ValueError("scheduledStartAt is required for TIMER mode")
        return self


class ShopGameUpdate(BaseModel):
    pattern: Optional[str] = None
    dynamicPattern: Optional[str] = None
    betAmount: Optional[Decimal] = Field(default=None, gt=0)
    totalWinning: Optional[Decimal] = Field(default=None, ge=0)
    totalCutPercent: Optional[Decimal] = Field(default=None, ge=10)
    startMode: Optional[GameStartMode] = None
    scheduledStartAt: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=1000)


class ShopGame(BaseModel):
    game_id: str = Field(default_factory=lambda: str(uuid4()))
    shopId: str
    branchId: str
    pattern: Optional[str] = None
    dynamicPattern: Optional[str] = None
    betAmount: Decimal
    totalWinning: Optional[Decimal] = None
    totalCutPercent: Decimal = Field(default=Decimal("10"), ge=10)
    totalCutAmount: Optional[Decimal] = None
    startMode: GameStartMode = "MANUAL"
    scheduledStartAt: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=1000)
    isFrozen: bool = False
    isPurchaseLocked: bool = False
    frozenByPhone: Optional[str] = None
    frozenByRole: Optional[Literal["system", "admin", "cashier"]] = None
    createdByPhone: str
    status: GameStatus = "PENDING"
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)


class GameParticipant(BaseModel):
    gp_id: str
    gameId: str
    playerPhone: str
    cartelaId: str
    isWinner: bool = False
    winAmount: Optional[Decimal] = None
    createdAt: datetime


class GameLifecycleRequest(BaseModel):
    action: Literal["START", "FREEZE", "UNFREEZE", "VOID"]
