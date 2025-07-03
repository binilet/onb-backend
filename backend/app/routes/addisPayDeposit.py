from fastapi import APIRouter,Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional
from datetime import datetime
from schemas.addispay.addisPayDepositRequest import AddisPayDepositRequest
from schemas.addispay.addisPayDepositCallback import AddisPayDepositCallback
from services.addisPay_deposit import get_addispay_deposit_request_by_date_range, get_addispay_deposit_callback_by_date_range
from dependencies.auth import get_db, get_current_active_user
from models.user import UserInDB  

router = APIRouter(prefix="/api/addispay_deposit", tags=["addispay_deposit_requests"])

@router.get("/request/by_date_range/", response_model=List[AddisPayDepositRequest])
async def get_addispay_deposits_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    print(start_date, end_date)
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    depositRequests = await get_addispay_deposit_request_by_date_range(db.addispaydepositrequests, start_date, end_date)
    return depositRequests

@router.get("/callback/by_date_range/", response_model=List[AddisPayDepositCallback])
async def get_addispay_deposit_callbacks_by_range(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    depositCallbacks = await get_addispay_deposit_callback_by_date_range(db.addispaydepositcallbacks, start_date, end_date)
    return depositCallbacks
