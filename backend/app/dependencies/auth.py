from datetime import datetime, timezone
from typing import Optional, Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from core.config import settings
from core.security import verify_password
from models.user import UserInDB
from schemas.userSchema import TokenData
from core.db import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)],db: AsyncIOMotorDatabase = Depends(get_db)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token,settings.SECRET_KEY,algorithms=[settings.ALGORITHM])
        phone:str = payload.get("phone")
        if phone is None:
            raise credentials_exception
        token_data = TokenData(phone=phone)
    except JWTError:
        raise credentials_exception
    
    user = await db.users.find_one({"phone":token_data.phone})
    if user is None:
        raise credentials_exception
    
    ban_until = user.get("banUntil") or user.get("ban_until")
    if ban_until and ban_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is banned until {}".format(ban_until),
        )
    _user = UserInDB(**user)
    return _user

async def get_current_active_user(current_user: Annotated[UserInDB, Depends(get_current_user)]) -> UserInDB:
    if not current_user.isActive:
        raise HTTPException(status_code=400, detail="Inactive user")
    if current_user.mustChangePassword:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change is required before accessing this resource",
        )
    return current_user

# async def get_current_admin_user(current_user: Annotated[UserInDB, Depends(get_current_active_user)]) -> UserInDB:
#     if current_user.role != "admin":
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="The user doesn't have enough privileges"
#         )
#     return current_user
