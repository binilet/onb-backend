from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from bson import ObjectId
from datetime import datetime,timedelta
from schemas.gameTransactionSchema import GameTransactionCreate, GameTransactionUpdate, GameTransactionInDB

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
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 10
) -> List[GameTransactionInDB]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)  # 23:59:59

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = games_collection.find({
        "date": {"$gte": query_start_date, "$lte": query_end_date}
    }).skip(skip).limit(limit)
    games = await cursor.to_list(length=limit)
    return [GameTransactionInDB(**game) for game in games]

async def get_undistributed_games(games_collection:AsyncIOMotorCollection)->List[GameTransactionInDB]:
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