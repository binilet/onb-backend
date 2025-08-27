from datetime import datetime, timedelta, timezone
from typing import Optional,List

from motor.motor_asyncio import AsyncIOMotorCollection
from bson import ObjectId

from models.user import UserInDB,UserWithBalance
from schemas.userSchema import UserSchema
from core.security import get_password_hash, verify_password
import base64

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
    if(user.role != "system" and user.role != "agent" and user.role != "admin"):
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
        users_cursor = users_collection.find()#.skip(skip).limit(limit)
    elif(current_user.role == "agent"):
        users_cursor = users_collection.find({"agentId": current_user.phone})#.skip(skip).limit(limit)
    elif(current_user.role == "admin"):
        users_cursor = users_collection.find({"adminId": current_user.phone,"role":"user"})#.skip(skip).limit(limit)


    users = await users_cursor.to_list()
    return [UserInDB(**user) for user in users] if users else []

async def get_users_by_role(users_collection: AsyncIOMotorCollection,credit_collection: AsyncIOMotorCollection, current_user: UserInDB,role:str, skip: int = 0,limit = 10) -> list[UserWithBalance]:
# Determine filter based on role
    if current_user.role == "system":
        query = {"role": role}
    elif current_user.role == "agent":
        query = {"agentId": current_user.phone, "role": role}
    elif current_user.role == "admin":
        query = {"adminId": current_user.phone, "role": role}
    else:
        return []
    
     # Fetch users
    #users = await users_collection.find(query).skip(skip).limit(limit).to_list(length=None)
    users = await users_collection.find(query).to_list(length=None)
    if not users:
        return []
    
    user_phones = [user["phone"] for user in users]

    credit_balances = await credit_collection.find({"phone": {"$in": user_phones}}).to_list(length=None)

    credit_map = {
        str(cb["phone"]): {
            "current_balance": cb.get("current_balance", 0),
            "previous_balance": cb.get("previous_balance", 0)
        }
        for cb in credit_balances
    }

    # Attach credit balances
    for user in users:
        user_phone_str = str(user["phone"])
        balances = credit_map.get(user_phone_str, {"current_balance": 0, "previous_balance": 0})
        user["current_balance"] = balances["current_balance"]
        user["previous_balance"] = balances["previous_balance"]
    
    # Return Pydantic models
    users_to_return = [UserWithBalance(**user) for user in users]
    #print(users_to_return)
    return users_to_return

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

async def get_users_by_phones(
    user_collection: AsyncIOMotorCollection, 
    phone_numbers: List[str]
) -> List[UserInDB]:
    """Fetch all users whose phone numbers are in the given list."""
    
    # Query using $in to match any phone in the list
    cursor = user_collection.find({"phone": {"$in": phone_numbers}})
    
    # Convert results to UserInDB objects (if using Pydantic)
    users = [UserInDB(**user) async for user in cursor]
    
    return users

def generate_referral_code(phone:str)->str:
    try:
        salted = f"X9{phone[::-1]}Z3"  # simple obfuscation
        encoded = base64.urlsafe_b64encode(salted.encode()).decode()
        return encoded
    except Exception as e:
        print(e)