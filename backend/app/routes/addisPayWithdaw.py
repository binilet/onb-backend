from fastapi import APIRouter,Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional
from datetime import datetime
from schemas.addispay.addisPayWithdrawRequest import AddisPayWithdrawalRequest
from schemas.addispay.addisPayWithdrawCallback import AddisPayWithdrawalCallback
from schemas.addispay.addisPayWithdrawResponse import AddisPayWithdrawalResponse
from services.addisPay_withdrawl import get_addispay_withdraw_request_by_date_range, get_addispay_withdraw_callback_by_date_range, get_addispay_withdraw_response_by_date_range

from dependencies.auth import get_db, get_current_active_user
from models.user import UserInDB  

router = APIRouter(prefix="/api/addispay_withdraw", tags=["addispay_withdraw_requests"])

@router.get("/request/by_date_range/", response_model=List[AddisPayWithdrawalRequest])
async def get_addispay_withdraw_request_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    depositRequests = await get_addispay_withdraw_request_by_date_range(db.addispaywithdrawlrequests, start_date, end_date)
    return depositRequests

@router.get("/callback/by_date_range/", response_model=List[AddisPayWithdrawalCallback])
async def get_addispay_withdraw_callbacks_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    depositCallbacks = await get_addispay_withdraw_callback_by_date_range(db.addispaywithdrawlcallbacks, start_date, end_date)
    return depositCallbacks

@router.get("/response/by_date_range/", response_model=List[AddisPayWithdrawalResponse])
async def get_addispay_withdraw_response_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    depositCallbacks = await get_addispay_withdraw_response_by_date_range(db.addispaywithdrawlresponses, start_date, end_date)
    return depositCallbacks
