from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from bson import ObjectId
from datetime import datetime,timedelta,timezone
from schemas.gameTransactionSchema import GameTransactionCreate, GameTransactionUpdate, GameTransactionInDB
from models.user import UserInDB

async def create_game_transaction(
    games_collection: AsyncIOMotorCollection, game: GameTransactionCreate
) -> Optional[GameTransactionInDB]:
    game_dict = game.model_dump()
    result = await games_collection.insert_one(game_dict)
    created_game = await games_collection.find_one({"_id": result.inserted_id})
    return GameTransactionInDB(**created_game) if created_game else None

async def get_game_transaction(
    games_collection: AsyncIOMotorCollection, game_id: str
) -> Optional[GameTransactionInDB]:
    game = await games_collection.find_one({"game_id": game_id})
    return GameTransactionInDB(**game) if game else None

async def update_game_transaction(
    games_collection: AsyncIOMotorCollection, game_id: str, update_data: GameTransactionUpdate
) -> Optional[GameTransactionInDB]:
    update_dict = update_data.model_dump(exclude_unset=True)
    await games_collection.update_one({"game_id": game_id}, {"$set": update_dict})
    updated_game = await games_collection.find_one({"game_id": game_id})
    return GameTransactionInDB(**updated_game) if updated_game else None

async def delete_game_transaction(
    games_collection: AsyncIOMotorCollection, game_id: str
) -> bool:
    result = await games_collection.delete_one({"game_id": game_id})
    return result.deleted_count > 0

async def get_games_by_date_range(
    games_collection: AsyncIOMotorCollection,
    users_collection: AsyncIOMotorCollection,
    current_user: UserInDB,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 10
) -> List[GameTransactionInDB]:

    tz = timezone(timedelta(hours=3))  # your local timezone (GMT+3)

    today_local = datetime.now(tz=tz).replace(hour=0, minute=0, second=0, microsecond=0)
    default_end_local = today_local + timedelta(days=1) - timedelta(seconds=1)

    # Local → UTC conversion
    query_start_date_local = start_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz) if start_date else today_local
    query_end_date_local = end_date.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=tz) if end_date else default_end_local

    query_start_date_utc = query_start_date_local.astimezone(timezone.utc)
    query_end_date_utc = query_end_date_local.astimezone(timezone.utc)

    query = {
        "date": {
            "$gte": query_start_date_utc,
            "$lte": query_end_date_utc
        }
    }

    user_phones = None
    if current_user.role == "admin":
        user_cursor = users_collection.find({"adminId": current_user.phone}, {"phone": 1})
        user_phones = [user["phone"] async for user in user_cursor]
        query["players"] = {"$in": user_phones}
    elif current_user.role == "agent":
        user_cursor = users_collection.find({"agentId": current_user.phone}, {"phone": 1})
        user_phones = [user["phone"] async for user in user_cursor]
        query["players"] = {"$in": user_phones}

    # Query games
    cursor = games_collection.find(query)  # can add .skip(skip).limit(limit)
    raw_games = await cursor.to_list(length=limit)

    filtered_games = []
    for game in raw_games:

        if "date" in game and isinstance(game["date"], datetime):
            # shift UTC → GMT+3
            game["date"] = game["date"] + timedelta(hours=3)

        if user_phones:
            game["players"] = [p for p in game["players"] if p in user_phones]
            if "winners" in game and game["winners"]:
                game["winners"] = [w for w in game["winners"] if w in user_phones]
        filtered_games.append(GameTransactionInDB(**game))

    return filtered_games

async def get_undistributed_games(games_collection:AsyncIOMotorCollection,game_id:str= None)->List[GameTransactionInDB]:
    if game_id:
        cursor = games_collection.find({
            "game_id": game_id,
            "is_void": False,
            "game_completed": True,
            "$or": [
                { "game_distributed": False },
                { "game_distributed": { "$exists": False } }
            ]
        })
    else:
        cursor = games_collection.find({
            "is_void": False,
            "game_completed": True,
            "$or": [
                { "game_distributed": False },
                { "game_distributed": { "$exists": False } }
            ]
        })
        
    games = await cursor.to_list()  # Adjust the length as needed
    return [GameTransactionInDB(**game) for game in games]

async def update_game_transaction_distributed_status(
    games_collection: AsyncIOMotorCollection, game_id: str, distrbuted: bool
) -> Optional[GameTransactionInDB]:
    await games_collection.update_one({"game_id": game_id}, {"$set": {"game_distributed": distrbuted}})
    updated_game = await games_collection.find_one({"game_id": game_id})
    return GameTransactionInDB(**updated_game) if updated_game else None