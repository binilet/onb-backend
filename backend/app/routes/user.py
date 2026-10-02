from fastapi import APIRouter, Depends, HTTPException,Query
from datetime import datetime
from typing import Optional
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
    SUBAGENT,
    SYSTEM,
    get_scoped_staff_user,
    require_roles,
    staff_scope_filter,
    inherited_owner_assignment,
    validate_assigned_cut,
)
from shop.audit import write_action_log


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
    existing = await db.users.find_one({"_id": ObjectId(user_id)})
    if existing is None:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role != SYSTEM:
        if current_user.id != user_id:
            raise HTTPException(status_code=403, detail="Staff may update only their own account")
        sensitive_fields = {
            "role",
            "shopId",
            "branchId",
            "agentId",
            "subagentId",
            "agentPercent",
            "adminId",
            "adminPercent",
            "parentPhone",
            "ownerPhone",
            "parentCutPercent",
        }
        requested_fields = set(user_update.model_dump(exclude_unset=True))
        if sensitive_fields.intersection(requested_fields):
            raise HTTPException(status_code=403, detail="Hierarchy assignments must use the authorized shop endpoints")
    
    update_data = user_update.model_dump(exclude_unset=True)
    owner_phone = update_data.pop("ownerPhone", None)
    requested_role = update_data.get("role")
    if requested_role == SYSTEM:
        raise HTTPException(status_code=403, detail="The system role cannot be assigned")
    if existing.get("role") == SYSTEM and requested_role not in {None, SYSTEM}:
        raise HTTPException(status_code=403, detail="The system account role cannot be changed")
    if current_user.role == SYSTEM and requested_role and requested_role != existing.get("role"):
        if requested_role not in {"user", AGENT, SUBAGENT, ADMIN, CASHIER, "employee"}:
            raise HTTPException(status_code=422, detail="Unsupported role")
        if requested_role == CASHIER:
            shop_id = update_data.get("shopId")
            branch_id = update_data.get("branchId")
            if not shop_id or not branch_id:
                raise HTTPException(status_code=422, detail="Cashiers require a shop and branch")
            branch = await db.shopBranches.find_one({"branch_id": branch_id, "shopId": shop_id})
            if branch is None:
                raise HTTPException(status_code=422, detail="The selected branch does not belong to the selected shop")
        update_data["parentPhone"] = None if requested_role == AGENT else current_user.phone
        if requested_role in {AGENT, SUBAGENT, "user", "employee"}:
            update_data.update({"shopId": None, "branchId": None, "adminId": None})
        elif requested_role == ADMIN:
            update_data.update({"branchId": None, "adminId": None})
        update_data["agentId"] = None
        if requested_role in {AGENT, SUBAGENT, ADMIN, CASHIER}:
            validate_assigned_cut(
                current_user,
                requested_role,
                update_data.get("parentCutPercent", existing.get("parentCutPercent")),
            )
    elif current_user.role == SYSTEM and "parentCutPercent" in update_data:
        validate_assigned_cut(current_user, existing.get("role", "user"), update_data["parentCutPercent"])
    if current_user.role == SYSTEM and owner_phone:
        ownership_role = requested_role or existing.get("role", "user")
        update_data.update(
            await inherited_owner_assignment(db, current_user, ownership_role, owner_phone)
        )
    user = await update_user(db.users, user_id=user_id, update_data=update_data)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if requested_role and requested_role != existing.get("role"):
        await write_action_log(
            db,
            current_user,
            "UPDATE",
            "STAFF_ROLE",
            user.phone,
            shop_id=user.shopId,
            branch_id=user.branchId,
            detail={"fromRole": existing.get("role"), "toRole": requested_role},
        )
    return user

@router.get("/all_users", response_model=list[UserInDB])
async def read_all_users(skip: int = 0,limit: int = 1000,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):

    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    scope = await staff_scope_filter(db, current_user)
    documents = await db.users.find(scope).skip(skip).limit(limit).to_list(length=limit)
    return [UserInDB(**user) for user in documents]

@router.get("/all_users_by_role", response_model=list[UserWithBalance])
async def read_all_users_by_role(
    role:str, skip: int = 0, limit: int = 100, startAt: Optional[datetime] = None, endAt: Optional[datetime] = None, phone: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    # if current_user.role != SYSTEM:
    #     raise HTTPException(
    #         status_code=403,
    #         detail="Scoped staff reads are available at /api/shop/staff; player balance reports are outside staff scope",
    #     )
    return await get_users_by_role(db.users, db.creditbalances, current_user, role=role, skip=skip, limit=limit, start_at=startAt, end_at=endAt, phone=phone)
    
@router.get("/generate-referral")
def generate_referral(phone:str=Query(...)):
    code = generate_referral_code(phone)
    #referral_url = f"https://hagere-online.com/signup?ref={code}"
    referral_url = f"https://t.me/HagereBingoBot?start={code}"
    return JSONResponse({"referralUrl":referral_url})
