from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClient
from typing import List,Optional,Dict
from datetime import datetime
from schemas.gameTransactionSchema import GameTransactionInDB, GameTransactionCreate, GameTransactionUpdate
from schemas.winningDistributionSchema import WinningDistributionInDB
from services.game_service import (
    create_game_transaction,
    get_game_transaction,
    update_game_transaction,
    delete_game_transaction,
    get_games_by_date_range,
)
from services.winningDistribution_service import (
    get_winning_distributions_by_date_range,
    get_distribution_summary_by_phone,approvDistributions
)
from core.winningDistribution import (
    calculate_winning_distribution
)
from dependencies.auth import get_current_active_user
from core.db import get_db,get_client
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
    if current_user.role != "admin" and current_user.role != "agent" and current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    games = await get_games_by_date_range(db.gametransactions,db.users,current_user, start_date, end_date, skip, limit)
    return games


@router.get("/distribute_winnings", response_model=List[WinningDistributionInDB])
async def game_distribution(
    game_id: Optional[str] = None,
    redistribute: Optional[bool] = False,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_client)
):
    try:
        if current_user.role != "system":
            raise HTTPException(status_code=403, detail="Not enough permissions")
    
        distributed_data = await calculate_winning_distribution(db,game_id,redistribute)
        return distributed_data
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error: {}".format(str(e)))
    

@router.get("/winning_distribution", response_model=List[WinningDistributionInDB])
async def get_winning_distribution(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    phone: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        if current_user.role != "admin" and current_user.role != "agent" and current_user.role != "system":
            raise HTTPException(status_code=403, detail="Not enough permissions")
    
        distributions = await get_winning_distributions_by_date_range(
            db.WinningDistributions,
            current_user,
            start_date,
            end_date,
            phone
        )
        return distributions
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error: {}".format(str(e)))

@router.get("/winning_summary", response_model=Dict[str, float])
async def get_winning_distribution(
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        if current_user.role != "admin" and current_user.role != "agent" and current_user.role != "system":
            raise HTTPException(status_code=403, detail="Not enough permissions")
    
        distributions = await get_distribution_summary_by_phone(
            db.WinningDistributions,
            current_user
        )
        return distributions
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error: {}".format(str(e)))

@router.put("/update_distribution/{game_id}", response_model=bool)
async def update_distribution_status(
    game_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        if current_user.role != "system":
            raise HTTPException(status_code=403, detail="Not enough permissions")
    
        return await approvDistributions(
            db.WinningDistributions,
            current_user,
            game_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error: {}".format(str(e)))