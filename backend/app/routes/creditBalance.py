from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional
from datetime import datetime
from schemas.creditBalance import CreditBalanceInDB
from schemas.transactionHistory import TransactionHistoryBase
from services.creditbalance_service import get_credit_balances_by_date_range,get_credit_balances_by_phone,get_credit_histories_by_phone
from dependencies.auth import get_db, get_current_active_user
from models.user import UserInDB

router = APIRouter(prefix="/api/credit_balances", tags=["credit_balances"])

@router.get("/by_date_range/", response_model=List[CreditBalanceInDB])
async def get_credit_balances_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    balances = await get_credit_balances_by_date_range(db.creditbalances, start_date, end_date, skip, limit)
    return balances

@router.get("/by_phone_number/", response_model=CreditBalanceInDB)
async def get_credit_balances_by_phone_number(
    phone:str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    balances = await get_credit_balances_by_phone(db.creditbalances, phone)
    return balances

@router.get("/history_by_phone_number/", response_model=List[TransactionHistoryBase])
async def get_credit_histories_by_phone_number(
    phone:str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    print('phone is: ' + phone)
    if current_user.role != "system" | current_user.role != "admin" | current_user.role != "agent":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    balances = await get_credit_histories_by_phone(db.transactionhistories, phone)
    return balances