from datetime import datetime, timedelta, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection
from bson import ObjectId

from models.user import UserInDB
from schemas.userSchema import UserSchema
from core.security import get_password_hash, verify_password

async def get_user(users_collection: AsyncIOMotorCollection, user_id: str) -> Optional[UserInDB]:
    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    return UserInDB(**user) if user else None

#the idea is that AsyncIOMotercollection will be of type that u need like users,tranasction ...
async def get_user_by_phone(users_collection: AsyncIOMotorCollection, phone: str) -> Optional[UserInDB]:
    user = await users_collection.find_one({"phone": phone})
    return UserInDB(**user) if user else None

async def get_user_by_username(users_collection: AsyncIOMotorCollection, username: str) -> Optional[UserInDB]:
    user = await users_collection.find_one({"username": username})
    return UserInDB(**user) if user else None

async def authenticate_user(users_collection: AsyncIOMotorCollection, phone:str,password:str) -> Optional[UserInDB]:
    user = await get_user_by_phone(users_collection,phone)
    if not user:
        return None
    if not verify_password(password,user.password):
        return None
    return user

async def create_user(users_collection: AsyncIOMotorCollection,user: UserSchema) -> UserInDB:
    hashed_password = get_password_hash(user.password)
    user_dict = user.model_dump()
    user_dict["password"] = hashed_password
    user_dict["pwd_change_count"] = 0
    d = datetime.now(timezone.utc)
    user_dict["pwd_change_date"] = d

    result = await users_collection.insert_one(user_dict)
    created_user = await users_collection.find_one({"_id": result.inserted_id})
    #created_user.pop("password", None)
    return UserInDB(**created_user)

async def update_user(users_collection: AsyncIOMotorCollection, user_id:str,update_data:dict) -> Optional[UserInDB]:
    await users_collection.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})
    updated_user = await users_collection.find_one({"_id": ObjectId(user_id)})
    return UserInDB(**updated_user) if updated_user else None

async def get_users(users_collection: AsyncIOMotorCollection,current_user: UserInDB, skip: int = 0,limit: int = 10) -> list[UserInDB]:
    users_cursor = None
    if(current_user.role == "system"):
        users_cursor = users_collection.find().skip(skip).limit(limit)
    elif(current_user.role == "agent"):
        users_cursor = users_collection.find({"agent_id": current_user.phone}).skip(skip).limit(limit)
    users = await users_cursor.to_list(length=limit)
    return [UserInDB(**user) for user in users] if users else []

async def get_users_by_role(users_collection: AsyncIOMotorCollection, current_user: UserInDB,role:str, skip: int = 0,limit = 10) -> list[UserInDB]:
    users_cursor = None
    if(current_user.role == "system"):
        users_cursor = users_collection.find({"role":role}).skip(skip).limit(limit)
    elif(current_user.role == "agent"):
        users_cursor = users_collection.find({"agent_id": current_user.phone,"role":"user"}).skip(skip).limit(limit)
    users = await users_cursor.to_list(length=limit)
    return [UserInDB(**user) for user in users] if users else []


async def increment_verification_count(users_collection: AsyncIOMotorCollection, user_id: str) -> Optional[UserInDB]:
    return await update_user(
        users_collection,
        user_id,
        {"$inc": {"verification_txt_count": 1}}
    )

async def ban_user(
    users_collection: AsyncIOMotorCollection, 
    user_id: str, 
    ban_duration: timedelta
) -> Optional[UserInDB]:
    return await update_user(
        users_collection,
        user_id,
        {"ban_until": datetime.now(timezone.utc) + ban_duration}
    )