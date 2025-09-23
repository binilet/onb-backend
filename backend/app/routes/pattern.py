from fastapi import APIRouter, Depends, HTTPException
from motor.motor_asyncio import AsyncIOMotorCollection,AsyncIOMotorDatabase

from typing import List
from schemas.pattern import PatternCreate, PatternUpdate, PatternInDB
from services.pattern_service import PatternService
from dependencies.auth import get_db, get_current_active_user
from models.user import UserInDB


router = APIRouter(prefix="/api/auto/patterns", tags=["Jackpot Patterns"])


@router.get("/", response_model=List[PatternInDB])
async def get_all_patterns(current_user: UserInDB = Depends(get_current_active_user),db: AsyncIOMotorDatabase = Depends(get_db)):
    return await PatternService.get_all(db.patterns)


@router.get("/{pattern_id}", response_model=PatternInDB)
async def get_pattern_by_id(pattern_id: str,current_user: UserInDB = Depends(get_current_active_user),db: AsyncIOMotorDatabase = Depends(get_db)):
    pattern = await PatternService.get_by_id(db.patterns, pattern_id)
    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return pattern


@router.post("/", response_model=PatternInDB)
async def create_pattern(pattern: PatternCreate, current_user: UserInDB = Depends(get_current_active_user),db: AsyncIOMotorDatabase = Depends(get_db)):
    return await PatternService.create(db.patterns, pattern)


@router.put("/{pattern_id}", response_model=PatternInDB)
async def update_pattern(pattern_id: str, pattern: PatternUpdate, current_user: UserInDB = Depends(get_current_active_user),db: AsyncIOMotorDatabase = Depends(get_db)):
    updated = await PatternService.update(db.patterns, pattern_id, pattern)
    if not updated:
        raise HTTPException(status_code=404, detail="Pattern not found")
    return updated
