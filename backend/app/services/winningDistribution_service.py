from motor.motor_asyncio import AsyncIOMotorCollection
from datetime import datetime, timedelta
from typing import Optional, List
from schemas.winningDistributionSchema import WinningDistributionInDB

async def insert_winning_distributions_bulk(collection: AsyncIOMotorCollection, distributions: List[WinningDistributionInDB]) -> None:
    """
    Insert multiple winning distributions into the database.
    """
    if distributions:
        await collection.insert_many([distribution.model_dump() for distribution in distributions])



async def get_winning_distributions_by_date_range(
    collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[WinningDistributionInDB]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start = start_date or today
    query_end = end_date or default_end

    cursor = collection.find({
        "date": {"$gte": query_start, "$lte": query_end}
    })

    results = await cursor.to_list(length=None)
    return [WinningDistributionInDB(**res) for res in results]

async def get_winning_distributions_by_game_id(
    collection: AsyncIOMotorCollection,
    game_id: str
) -> List[WinningDistributionInDB]:
    cursor = collection.find({ "gameId": game_id })
    results = await cursor.to_list(length=None)
    return [WinningDistributionInDB(**res) for res in results]

async def get_winning_summary(collection: AsyncIOMotorCollection):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    match_stage = {
        "$match": {
            "date": { "$gte": start_of_year }
        }
    }

    project_stage = {
        "$project": {
            "amount": 1,
            "date": 1,
            "day": { "$dateToString": { "format": "%Y-%m-%d", "date": "$date" } },
            "week": { "$isoWeek": "$date" },
            "month": { "$month": "$date" },
            "year": { "$year": "$date" }
        }
    }

    group_stage = {
        "$group": {
            "_id": None,
            "dailyWinning": {
                "$sum": {
                    "$cond": [{ "$eq": ["$day", today.strftime("%Y-%m-%d")] }, "$amount", 0]
                }
            },
            "weeklyWinning": {
                "$sum": {
                    "$cond": [
                        {
                            "$and": [
                                { "$gte": ["$date", start_of_week] },
                                { "$lte": ["$date", now] }
                            ]
                        },
                        "$amount",
                        0
                    ]
                }
            },
            "monthlyWinning": {
                "$sum": {
                    "$cond": [
                        {
                            "$and": [
                                { "$gte": ["$date", start_of_month] },
                                { "$lte": ["$date", now] }
                            ]
                        },
                        "$amount",
                        0
                    ]
                }
            },
            "yearToDateWinning": {
                "$sum": "$amount"
            }
        }
    }

    pipeline = [match_stage, project_stage, group_stage]

    result = await collection.aggregate(pipeline).to_list(length=1)
    return result[0] if result else {
        "dailyWinning": 0,
        "weeklyWinning": 0,
        "monthlyWinning": 0,
        "yearToDateWinning": 0
    }


