from fastapi import APIRouter, HTTPException, Depends, Query
#from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from motor.motor_asyncio import AsyncIOMotorDatabase

from datetime import datetime
from schemas.autoGame import AutoGameCreate, AutoGameUpdate, AutoGameDB
from services.autoGame_service import create_game, update_game, get_by_id, get_by_date_range,create_or_update_game, get_game_player_owner_stats
from dependencies.auth import get_db, get_current_active_user
from models.user import UserInDB
from typing import Optional

router = APIRouter(prefix="/api/autoGames", tags=["auto_games"])


@router.post("/create", response_model=AutoGameDB)
async def create_autogame(
    game: AutoGameCreate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if not current_user.role == "system":
        raise HTTPException(status_code=403, detail="Not authorized to create games")
    return await create_game(db.autoGames, game)

@router.post("/create_or_update_game", response_model=AutoGameDB)
async def create_or_update_autogame(
    game: AutoGameCreate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if not current_user.role == "system":
        raise HTTPException(status_code=403, detail="Not authorized to create games")
    return await create_or_update_game(db.autoGames, game)


@router.put("/update/{game_id}", response_model=AutoGameDB)
async def edit_autogame(
    game_id: str,
    updates: AutoGameUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    
    if not current_user.role == "system":
        raise HTTPException(status_code=403, detail="Not authorized to create games")
    
    updated = await update_game(db.autoGames, game_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Game not found")
    return updated


@router.get("/fetch/{game_id}", response_model=AutoGameDB)
async def get_autogame_by_id(
    game_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    
    if not current_user.role == "system":
        raise HTTPException(status_code=403, detail="Not authorized to update games")
    game = await get_by_id(db.autoGames, game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game


@router.get("/fetch-range", response_model=list[AutoGameDB])
async def get_autogames_by_date_range(
    start: Optional[datetime] = Query(None, description="Start date in local time (GMT+3)"),
    end: Optional[datetime] = Query(None, description="Optional end date in local time (GMT+3)"),
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    
    if not current_user.role == "system":
        raise HTTPException(status_code=403, detail="Not authorized to get games")
    return await get_by_date_range(db.autoGames, start, end)


@router.get("/stats/{game_id}")
async def get_game_stats(
    game_id: str,
    #current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    #if current_user.role != "system":
        #raise HTTPException(status_code=403, detail="Not authorized to view stats")
        
    stats = await get_game_player_owner_stats(db, game_id)
    if stats is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return stats
