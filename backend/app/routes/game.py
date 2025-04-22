from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List,Optional
from datetime import datetime
from schemas.gameTransactionSchema import GameTransactionInDB, GameTransactionCreate, GameTransactionUpdate
from services.game_service import (
    create_game_transaction,
    get_game_transaction,
    update_game_transaction,
    delete_game_transaction,
    get_games_by_date_range,
)
from dependencies.auth import get_current_active_user
from core.db import get_db
from models.user import UserInDB

router = APIRouter(prefix="/api/games", tags=["games"])

@router.post("/", response_model=GameTransactionInDB, status_code=status.HTTP_201_CREATED)
async def create_game(
    game: GameTransactionCreate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    created_game = await create_game_transaction(db.gametransactions, game)
    if not created_game:
        raise HTTPException(status_code=400, detail="Failed to create game transaction")
    return created_game

@router.get("/game_by_id/{game_id}", response_model=GameTransactionInDB)
async def get_game(
    game_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    
    if current_user.role != "system" or current_user.role != "agent":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    game = await get_game_transaction(db.gametransactions, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game transaction not found")
    return game

@router.patch("/{game_id}", response_model=GameTransactionInDB)
async def update_game(
    game_id: str,
    game_update: GameTransactionUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    updated_game = await update_game_transaction(db.gametransactions, game_id, game_update)
    if not updated_game:
        raise HTTPException(status_code=404, detail="Game transaction not found")
    return updated_game

@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    success = await delete_game_transaction(db.gametransactions, game_id)
    if not success:
        raise HTTPException(status_code=404, detail="Game transaction not found")

@router.get("/by_date_range/", response_model=List[GameTransactionInDB])
async def get_games_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    games = await get_games_by_date_range(db.gametransactions, start_date, end_date, skip, limit)
    return games