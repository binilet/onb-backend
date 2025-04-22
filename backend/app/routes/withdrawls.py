from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional
from datetime import datetime
from schemas.santimWithdrawls import SantimWithdrawlRequestInDB, SantimWithdrawlStatusInDB
from services.santim_withdrawls import get_santim_withdrawal_requests_by_date_range, get_santim_withdrawal_statuses_by_date_range
from dependencies.auth import get_db, get_current_active_user
from models.user import UserInDB

router = APIRouter(prefix="/api/santim_withdrawals", tags=["santim_withdrawals"])

@router.get("/requests/by_date_range/", response_model=List[SantimWithdrawlRequestInDB])
async def get_santim_withdrawal_requests_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    withdrawals = await get_santim_withdrawal_requests_by_date_range(db.santimwithdrawlrequests, start_date, end_date, skip, limit)
    return withdrawals

@router.get("/statuses/by_date_range/", response_model=List[SantimWithdrawlStatusInDB])
async def get_santim_withdrawal_statuses_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    statuses = await get_santim_withdrawal_statuses_by_date_range(db.santimwithdrawlstatuses, start_date, end_date, skip, limit)
    return statuses