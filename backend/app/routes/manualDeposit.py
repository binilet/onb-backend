from fastapi import APIRouter, Depends, Query
from datetime import datetime
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status

from models.user import UserInDB  
from services.manual_pay import fetch_manual_deposits,approve_manual_deposit
from schemas.manualPay.manual_deposit import ManualDepositRequest
from motor.motor_asyncio import AsyncIOMotorClient

from dependencies.auth import get_current_active_user
from core.db import get_db,get_client
from fastapi import Path

router = APIRouter(prefix="/api/manual-deposits", tags=["manual-deposits"])

@router.get("/requests", response_model=List[ManualDepositRequest])
async def get_manual_deposits(
    phone: Optional[str] = None,
    processed: Optional[bool] = None,
    startDate: Optional[datetime] = Query(None),
    endDate: Optional[datetime] = Query(None),
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    #limit for sys admin
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return await fetch_manual_deposits(db.manualdepositrequests, startDate, endDate, phone, processed)



@router.patch("/requests/{deposit_id}/approve")
async def approve_deposit(
    deposit_id: str = Path(..., title="The ID of the deposit to approve"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    client: AsyncIOMotorClient = Depends(get_client),
    current_user: UserInDB = Depends(get_current_active_user)
     ):
    if current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    success = await approve_manual_deposit(client,db.manualdepositrequests, db.creditbalances, db.transactionhistories,deposit_id)
    return {"success": success, "message": "Deposit approved." if success else "No changes made."}

