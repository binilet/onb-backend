from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class DashboardTotals(BaseModel):
    completedGames: int = 0
    totalBets: Decimal = Decimal("0")
    totalWinnings: Decimal = Decimal("0")
    totalCut: Decimal = Decimal("0")
    cartelasSold: int = 0


class DashboardCutPeriods(BaseModel):
    today: Decimal = Decimal("0")
    week: Decimal = Decimal("0")
    month: Decimal = Decimal("0")
    year: Decimal = Decimal("0")


class DashboardOperations(BaseModel):
    pendingGames: int = 0
    activeGames: int = 0
    pendingDeposits: int = 0
    pendingWithdrawals: int = 0


class DashboardTrendPoint(BaseModel):
    date: str
    games: int = 0
    bets: Decimal = Decimal("0")
    winnings: Decimal = Decimal("0")
    cut: Decimal = Decimal("0")


class DashboardRecentGame(BaseModel):
    gameId: str
    gameName: str
    shopId: str
    branchId: str
    status: str
    betAmount: Decimal = Decimal("0")
    totalBets: Decimal = Decimal("0")
    totalWinning: Decimal = Decimal("0")
    totalCutAmount: Decimal = Decimal("0")
    createdAt: datetime


class ShopDashboard(BaseModel):
    startAt: datetime
    endAt: datetime
    currentBalance: Decimal = Decimal("0")
    totals: DashboardTotals = Field(default_factory=DashboardTotals)
    cuts: DashboardCutPeriods = Field(default_factory=DashboardCutPeriods)
    operations: DashboardOperations = Field(default_factory=DashboardOperations)
    gameStatuses: dict[str, int] = Field(default_factory=dict)
    trend: list[DashboardTrendPoint] = Field(default_factory=list)
    recentGames: list[DashboardRecentGame] = Field(default_factory=list)
    shopId: Optional[str] = None
    branchId: Optional[str] = None
