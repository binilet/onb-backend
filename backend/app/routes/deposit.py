from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional
from datetime import datetime
from schemas.santimDepositRequest import SantimDepositRequestInDB
from schemas.santimDepositStatus import SantimDepositStatusInDB
from services.santim_deposit import get_santim_deposits_by_date_range, get_santim_deposit_statuses_by_date_range
from dependencies.auth import get_db, get_current_active_user
from models.user import UserInDB  # Adjust import based on your structure

router = APIRouter(prefix="/api/santim_deposit", tags=["santim_deposit_requests"])

@router.get("/request/by_date_range/", response_model=List[SantimDepositRequestInDB])
async def get_santim_deposits_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    deposits = await get_santim_deposits_by_date_range(db.santimdepositrequests, start_date, end_date, skip, limit)
    return deposits

@router.get("/status/by_date_range/", response_model=List[SantimDepositStatusInDB])
async def get_santim_deposit_statuses_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    statuses = await get_santim_deposit_statuses_by_date_range(db.santimdepositstatuses, start_date, end_date, skip, limit)
    return statuses