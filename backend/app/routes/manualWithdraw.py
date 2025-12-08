from fastapi import APIRouter, Depends, Query
from datetime import datetime
from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException, status

from models.user import UserInDB  
from services.manual_pay import getManualWithdrawRequests,approve_manual_withdraw_request,void_manual_withdraw_request
from schemas.manualPay.manual_request import ManualWithRequest
from motor.motor_asyncio import AsyncIOMotorClient

from dependencies.auth import get_current_active_user
from core.db import get_db,get_client
from fastapi import Path

router = APIRouter(prefix="/api/manual-withdraws", tags=["manual-withdraws"])

@router.get("/requests", response_model=List[ManualWithRequest])
async def get_manual_deposits(
    phone: Optional[str] = None,
    approved: Optional[bool] = None,
    startDate: Optional[datetime] = Query(None),
    endDate: Optional[datetime] = Query(None),
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    #limit for sys admin
    if current_user.role != "system" and current_user.role != "employee":
       raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return await getManualWithdrawRequests(db.manualwithrequests, startDate, endDate, phone, approved)

@router.patch("/requests/{withdraw_id}/approve")
async def approve_withdrawl(
    withdraw_id: str = Path(..., title="The ID of the deposit to approve"),
    telebirrReference: str = Query(...,title="the telebirr deposit reference"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_active_user),
    client: AsyncIOMotorClient = Depends(get_client),
     ):
    print('starting withdrawal request approval ...')
    if current_user.role != "system" and current_user.role != "employee":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    print(withdraw_id)
    print(telebirrReference)
    
    success = await approve_manual_withdraw_request(client,db.manualwithrequests, db.creditbalances, db.transactionhistories,current_user,withdraw_id,telebirrReference)
    return {"success": success, "message": "Deposit approved." if success else "No changes made."}

@router.patch("/void_requests/{withdraw_id}/void")
async def void_withdrawl(
    withdraw_id: str = Path(..., title="The ID of the deposit to approve"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: UserInDB = Depends(get_current_active_user),
    client: AsyncIOMotorClient = Depends(get_client),
     ):
    print('starting withdrawal request voiding ...')
    if current_user.role != "system" and current_user.role != "employee":
        raise HTTPException(status_code=403, detail="Not enough permissions")

    success = await void_manual_withdraw_request(client,db.manualwithrequests, db.creditbalances, db.transactionhistories,current_user,withdraw_id)
    return {"success": success, "message": "Deposit voided." if success else "No changes made."}