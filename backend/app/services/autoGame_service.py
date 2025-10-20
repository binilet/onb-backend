from datetime import datetime, timedelta, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ReturnDocument
from schemas.autoGame import AutoGameCreate, AutoGameUpdate

LOCAL_TZ = timezone(timedelta(hours=3))  # GMT+3


def convert_local_to_utc(local_time: datetime) -> datetime:
    """Convert GMT+3 local datetime to UTC."""
    if local_time.tzinfo is None:
        local_time = local_time.replace(tzinfo=LOCAL_TZ)
    return local_time.astimezone(timezone.utc)


def convert_utc_to_local(utc_time: datetime) -> datetime:
    """Convert UTC datetime to GMT+3 local time."""
    if utc_time.tzinfo is None:
        utc_time = utc_time.replace(tzinfo=timezone.utc)
    return utc_time.astimezone(LOCAL_TZ)


def normalize_game_result(game: dict) -> dict:
    """Attach id and convert UTC->Local before returning."""
    game["id"] = str(game["_id"])
    game["startTimeLocal"] = convert_utc_to_local(game["startTimeUtc"])
    return game


async def create_or_update_game(
    collection: AsyncIOMotorCollection,
    game_data: AutoGameCreate,
):
    """
    Create a new game if gameId does not exist, otherwise update it.
    Expects game_data to already include gameId and other fields.
    """

    if not game_data.pattern and not game_data.dynamicPattern:
        raise ValueError("Either pattern or dynamicPattern must be provided.")

    #data = game_data.dict()  # ✅ correct way with Pydantic
    data = game_data.dict(exclude_unset=True)

    now = datetime.utcnow()

    # handle time conversion
    if "startTimeLocal" in data:
        print('setting local time: ')
        data["startTimeUtc"] = convert_local_to_utc(data["startTimeLocal"])

    print(f"utc time set to: {data['startTimeUtc']}")
    print(f"local time set to: {data['startTimeLocal']}")

    data["updatedAt"] = now

    # upsert (insert if not exists, update if exists)
    result = await collection.find_one_and_update(
        {"gameId": data["gameId"]},
        {"$setOnInsert": {"createdAt": now}, "$set": data},
        upsert=True,
        return_document=ReturnDocument.AFTER,  # ✅ correct usage
    )

    return normalize_game_result(result)

async def create_game(collection: AsyncIOMotorCollection, game: AutoGameCreate):
    game_dict = game.dict()
    game_dict["startTimeUtc"] = convert_local_to_utc(game.startTimeLocal)
    game_dict["createdAt"] = datetime.utcnow()
    game_dict["updatedAt"] = datetime.utcnow()

    result = await collection.insert_one(game_dict)
    game_dict["_id"] = result.inserted_id
    return normalize_game_result(game_dict)


async def update_game(collection: AsyncIOMotorCollection, game_id: str, updates: AutoGameUpdate):
    update_data = updates.dict(exclude_unset=True)

    if "startTimeLocal" in update_data:
        update_data["startTimeUtc"] = convert_local_to_utc(update_data["startTimeLocal"])

    update_data["updatedAt"] = datetime.utcnow()

    result = await collection.find_one_and_update(
        {"_id": ObjectId(game_id)},
        {"$set": update_data},
        return_document=True,
    )

    if not result:
        return None

    return normalize_game_result(result)


async def get_by_id(collection: AsyncIOMotorCollection, game_id: str):
    result = await collection.find_one({"_id": ObjectId(game_id)})
    if not result:
        return None
    return normalize_game_result(result)


from datetime import datetime, timedelta, timezone
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorCollection

LOCAL_TZ = timezone(timedelta(hours=3))  # GMT+3


async def get_by_date_range(
    collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """Get games in a date range (UTC). 
    - If both start and end are None → today's games (local time).
    - If only start is given → same-day games.
    - If both start and end are given → range.
    """
    
    if start_date is None and end_date is None:
        # Use today in LOCAL_TZ
        today_local = datetime.now(LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = today_local
        end_date = today_local + timedelta(days=1)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=LOCAL_TZ)
        
    start_utc = start_date.astimezone(timezone.utc)

    if end_date:
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=LOCAL_TZ)
        end_utc = end_date.astimezone(timezone.utc) 
    else:
        # only start_date given → cover full local day
        end_utc = (start_date + timedelta(days=1)).astimezone(timezone.utc)

    print(f"Fetching games from {start_utc} to {end_utc} UTC")
    cursor = collection.find({
        "startTimeUtc": {"$gte": start_utc, "$lt": end_utc}
    })

    results = []
    async for doc in cursor:
        results.append(normalize_game_result(doc))

    return results
