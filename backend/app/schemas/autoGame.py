from typing import List, Optional, Literal
from pydantic import BaseModel,Field
from datetime import datetime


class PlayerBoard(BaseModel):
    playerPhone: str
    boardIds: List[int]


class GameWinner(BaseModel):
    playerPhone: str
    boardId: int
    winningAmount: float


class AutoGameBase(BaseModel):
    gameId: str
    gameName: str
    betAmount: float
    totalWinning: float = 0
    boardIds: List[int] = Field(default_factory=list)
    callList: List[int] = Field(default_factory=list)
    gameStatus: Literal["scheduled", "running", "completed"] = "scheduled"
    isDistributed: bool = False
    isVoid: bool = False
    gameNote: Optional[str] = None
    pattern: str  # ObjectId string
    playerBoards: List[PlayerBoard] = Field(default_factory=list)
    gameWinners: List[GameWinner] = Field(default_factory=list)
    startTimeLocal: datetime
    startTimeUtc: Optional[datetime] = None  # filled automatically
    displayStartTime: str  # formatted string for display


class AutoGameCreate(AutoGameBase):
    pass


class AutoGameUpdate(BaseModel):
    gameName: Optional[str] = None
    betAmount: Optional[float] = None
    totalWinning: Optional[float] = None
    boardIds: Optional[List[int]] = Field(default_factory=list)
    callList: Optional[List[int]] = Field(default_factory=list)
    playerBoards: Optional[List[PlayerBoard]] = Field(default_factory=list)
    gameWinners: Optional[List[GameWinner]] = Field(default_factory=list)
    gameStatus: Optional[Literal["scheduled", "running", "completed"]] = None
    isDistributed: Optional[bool] = None
    isVoid: Optional[bool] = None
    gameNote: Optional[str] = None
    pattern: Optional[str] = None
    startTimeLocal: Optional[datetime] = None
    displayStartTime: str


class AutoGameDB(AutoGameBase):
    id: str
    createdAt: datetime
    updatedAt: datetime

    class Config:
        orm_mode = True
