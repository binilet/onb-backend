from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class WinningDistributionInDB(BaseModel):
    gameId: str
    date: Optional[datetime] = None
    totalPlayers: int
    betAmount: float
    totalWinning: float
    distributable: float
    yourPlayers: int
    yourPercent: float
    amount: float
    phone:str
    owner:str
    role:str
    deposited:bool
    approved:bool=False
    approvedBy: Optional[str] = None
    approvedDate: Optional[datetime] = None
    note: Optional[str] = ""

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
