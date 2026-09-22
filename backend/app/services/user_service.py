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
    if(user.role != "system" and user.role != "agent" and user.role != "subagent" and user.role != "admin" and user.role != "cashier" and user.role != "employee"):
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

async def get_users_by_role(
    users_collection: AsyncIOMotorCollection,
    credit_collection: AsyncIOMotorCollection,
    current_user: UserInDB,
    role: str,
    skip: int = 0,
    limit: int = 10
) -> list[UserWithBalance]:
    # Determine filter based on role
    if current_user.role == "system":
        if role == "agent":
            query = {"role": {"$in": [role, "system", "employee"]}}
        else:
            query = {"role": {"$in": [role]}}
    elif current_user.role == "agent":
        if role == "user":
            query = {"agentId": current_user.phone, "role": {"$in": ["user", "admin"]}}
        else:
            query = {"agentId": current_user.phone, "role": role}
    elif current_user.role == "admin":
        query = {"adminId": current_user.phone, "role": role}
    else:
        return []

    # For agent requesting users, we need to also include users under their admins
    if current_user.role == "agent" and role == "user":
        # Use an aggregation to gather direct users + users under agent's admins
        pipeline = [
            # First: find admins under this agent
            {"$match": {"agentId": current_user.phone, "role": "admin"}},
            # Collect admin phones
            {"$group": {"_id": None, "admin_phones": {"$push": "$phone"}}},
            # Lookup users that belong to those admins OR directly to the agent
            {"$lookup": {
                "from": users_collection.name,
                "let": {"admin_phones": "$admin_phones"},
                "pipeline": [
                    {"$match": {"$expr": {"$and": [
                        {"$eq": ["$role", "user"]},
                        {"$or": [
                            {"$eq": ["$agentId", current_user.phone]},
                            {"$in": ["$adminId", "$$admin_phones"]}
                        ]}
                    ]}}}
                ],
                "as": "all_users"
            }},
            {"$unwind": "$all_users"},
            {"$replaceRoot": {"newRoot": "$all_users"}}
        ]

        # Also include direct users under the agent (in case there are no admins)
        # We'll use a simpler approach: two queries merged, but keep it efficient
        # by only fetching phones first, then doing a single $lookup for balances
        admin_docs = await users_collection.find(
            {"agentId": current_user.phone, "role": "admin"},
            {"phone": 1, "_id": 0}
        ).to_list(length=None)
        admin_phones = [doc["phone"] for doc in admin_docs]

        user_query = {"$or": [
            {"agentId": current_user.phone, "role": "user"},
        ]}
        if admin_phones:
            user_query["$or"].append({"adminId": {"$in": admin_phones}, "role": "user"})

        match_stage = {"$match": user_query}
    else:
        match_stage = {"$match": query}

    # Build the aggregation pipeline with $lookup for credit balances
    pipeline = [
        match_stage,
        # Join with creditbalances collection
        {"$lookup": {
            "from": credit_collection.name,
            "localField": "phone",
            "foreignField": "phone",
            "as": "credit_info"
        }},
        # Flatten the credit_info (will be empty array if no match)
        {"$addFields": {
            "current_balance": {
                "$ifNull": [{"$arrayElemAt": ["$credit_info.current_balance", 0]}, 0]
            },
            "previous_balance": {
                "$ifNull": [{"$arrayElemAt": ["$credit_info.previous_balance", 0]}, 0]
            },
            "promo_balance": {
                "$ifNull": [{"$arrayElemAt": ["$credit_info.promo_balance", 0]}, 0]
            }
        }},
        # Remove the joined array to keep output clean
        {"$project": {"credit_info": 0}},
        # Sort by current_balance descending (server-side)
        {"$sort": {"current_balance": -1}},
        # Pagination
        {"$skip": skip}
        # {"$limit": limit}
    ]

    results = await users_collection.aggregate(pipeline).to_list()

    if not results:
        return []

    return [UserWithBalance(**doc) for doc in results]

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
