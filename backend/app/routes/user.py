from fastapi import APIRouter, Depends, HTTPException,Query
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from dependencies.auth import get_current_active_user
from models.user import UserInDB,UserWithBalance
from schemas.userSchema import UserUpdate
from services.user_service import get_user, update_user, get_users,get_users_by_role,generate_referral_code
from core.db import get_db


router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me", response_model=UserInDB)
async def read_users_me(current_user: UserInDB = Depends(get_current_active_user)):
    return current_user

@router.get("/user_by_id/{user_id}", response_model=UserInDB)
async def read_user(
    user_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    user = await get_user(db.users, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.patch("/{user_id}", response_model=UserInDB)
async def update_user_details(
    user_id: str,
    user_update: UserUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.id != user_id and current_user.role != "system":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    update_data = user_update.model_dump(exclude_unset=True)
    print(update_data)
    user = await update_user(db.users, user_id=user_id, update_data=update_data)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/all_users", response_model=list[UserInDB])
async def read_all_users(skip: int = 0,limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):

    if current_user.role == "user":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    users = await get_users(db.users,current_user, skip=skip, limit=limit)
    return users

@router.get("/all_users_by_role", response_model=list[UserWithBalance])
async def read_all_users_by_role(
    role:str,skip: int = 0,limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):

    if current_user.role == "user":
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    users = await get_users_by_role(db.users,db.creditbalances,current_user,role=role, skip=skip, limit=limit)

    return users
    
@router.get("/generate-referral")
def generate_referral(phone:str=Query(...)):
    code = generate_referral_code(phone)
    referral_url = f"https://hagere-online.com/signup?ref={code}"
    return JSONResponse({"referralUrl":referral_url})