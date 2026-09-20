from fastapi import APIRouter, Depends, HTTPException,Query
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from dependencies.auth import get_current_active_user, get_current_user
from models.user import UserInDB,UserWithBalance
from schemas.userSchema import UserUpdate
from services.user_service import get_user, update_user, get_users,get_users_by_role,generate_referral_code
from core.db import get_db
from shop.authorization import (
    ADMIN,
    AGENT,
    CASHIER,
    SYSTEM,
    get_scoped_staff_user,
    require_roles,
    staff_scope_filter,
)


router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me", response_model=UserInDB)
async def read_users_me(current_user: UserInDB = Depends(get_current_user)):
    return current_user

@router.get("/user_by_id/{user_id}", response_model=UserInDB)
async def read_user(
    user_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.id == user_id:
        return current_user
    if current_user.role == SYSTEM:
        user = await get_user(db.users, user_id=user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    require_roles(current_user, AGENT, ADMIN, CASHIER)
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserInDB(**(await get_scoped_staff_user(db, current_user, user["phone"])))

@router.patch("/{user_id}", response_model=UserInDB)
async def update_user_details(
    user_id: str,
    user_update: UserUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    if current_user.role != SYSTEM:
        if current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Staff may update only their own account")
        sensitive_fields = {"role", "shopId", "branchId", "agentId", "adminId"}
        requested_fields = set(user_update.model_dump(exclude_unset=True))
        if sensitive_fields.intersection(requested_fields):
            raise HTTPException(status_code=403, detail="Hierarchy assignments must use the authorized shop endpoints")
    
    update_data = user_update.model_dump(exclude_unset=True)
    user = await update_user(db.users, user_id=user_id, update_data=update_data)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.get("/all_users", response_model=list[UserInDB])
async def read_all_users(skip: int = 0,limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):

    require_roles(current_user, SYSTEM, AGENT, ADMIN, CASHIER)
    scope = await staff_scope_filter(db, current_user)
    documents = await db.users.find(scope).skip(skip).limit(limit).to_list(length=limit)
    return [UserInDB(**user) for user in documents]

@router.get("/all_users_by_role", response_model=list[UserWithBalance])
async def read_all_users_by_role(
    role:str,skip: int = 0,limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    require_roles(current_user, SYSTEM, AGENT, ADMIN, CASHIER)
    # if current_user.role != SYSTEM:
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Scoped staff reads are available at /api/shop/staff; player balance reports are outside staff scope",
    #     )
    return await get_users_by_role(db.users, db.creditbalances, current_user, role=role, skip=skip, limit=limit)
    
@router.get("/generate-referral")
def generate_referral(phone:str=Query(...)):
    code = generate_referral_code(phone)
    #referral_url = f"https://hagere-online.com/signup?ref={code}"
    referral_url = f"https://t.me/HagereBingoBot?start={code}"
    return JSONResponse({"referralUrl":referral_url})
