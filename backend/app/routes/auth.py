from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.config import settings
from core.db import get_db
from core.security import create_access_token, get_password_hash, verify_password
from dependencies.auth import get_current_user

from models.user import UserInDB
from schemas.userSchema import PasswordChangeRequest, UserSchema,UserLogin, Token
from services.user_service import (
    authenticate_user,
    create_user,
    get_user_by_phone,
    get_user_by_username,
    ban_user,
    increment_verification_count
)

router = APIRouter(prefix="/api/auth",tags=["auth"])

@router.post("/register",response_model=UserInDB)
async def register(user:UserSchema, db:AsyncIOMotorDatabase  = Depends(get_db)):
    try:
        if user.role not in (None, "user"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Staff accounts must be created by an authorized shop endpoint")
        db_user = await get_user_by_phone(db.users,phone=user.phone)
        if db_user:
            raise HTTPException(status_code=4,detail="Phone already registered")
        
        db_user = await get_user_by_username(db.users, username=user.username)
        if db_user:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        return await create_user(db.users, user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error: {}".format(str(e)))

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncIOMotorDatabase = Depends(get_db)):
    user = await authenticate_user(db.users, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.isActive:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token_expires = timedelta(minutes=max(settings.ACCESS_TOKEN_EXPIRE_MINUTES, 60))
    access_token = create_access_token(data={"phone":user.phone,"role":user.role,"agentId":user.agentId},expires_delta=access_token_expires)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/change-password")
async def change_password(
    payload: PasswordChangeRequest,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not current_user.isActive:
        raise HTTPException(status_code=400, detail="Inactive user")
    if not verify_password(payload.currentPassword, current_user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.users.update_one(
        {"phone": current_user.phone},
        {"$set": {"password": get_password_hash(payload.newPassword), "mustChangePassword": False}},
    )
    return {"message": "Password changed"}

@router.post("/request-verification/{phone}")
async def request_verification(phone: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    user = await get_user_by_phone(db.users, phone=phone)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.verification_txt_count >= settings.MAX_VERIFICATION_ATTEMPTS:
        await ban_user(db.users, str(user.id), timedelta(hours=1))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Account temporarily banned."
        )
    
    await increment_verification_count(db.users, str(user.id))
    return {"message": "Verification code sent (simulated)"}
