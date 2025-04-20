from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class GameTransactionBase(BaseModel):
    game_id: str
    date: datetime
    number_of_players: int
    bet_amount: float
    total_winning: float
    cut_percent: float
    cut_amount: float
    player_winning: float
    winners: Optional[List[str]] = None
    is_void: bool
    number_of_calls: Optional[int] = None
    winner_board_id: Optional[str] = None
    players: List[str]
    game_completed: bool
    note: Optional[str] = None

class GameTransactionCreate(GameTransactionBase):
    pass

class GameTransactionUpdate(BaseModel):
    date: Optional[datetime] = None
    number_of_players: Optional[int] = None
    bet_amount: Optional[float] = None
    total_winning: Optional[float] = None
    cut_percent: Optional[float] = None
    cut_amount: Optional[float] = None
    player_winning: Optional[float] = None
    winners: Optional[List[str]] = None
    is_void: Optional[bool] = None
    number_of_calls: Optional[int] = None
    winner_board_id: Optional[str] = None
    players: Optional[List[str]] = None
    game_completed: Optional[bool] = None
    note: Optional[str] = None

class GameTransactionInDB(GameTransactionBase):
    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()  # Convert datetime to ISO 8601 string
        }