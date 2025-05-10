from motor.motor_asyncio import AsyncIOMotorCollection
from datetime import datetime, timedelta
from typing import Optional, List,Dict
from schemas.winningDistributionSchema import WinningDistributionInDB
from models.user import UserInDB

async def insert_winning_distributions_bulk(collection: AsyncIOMotorCollection, distributions: List[WinningDistributionInDB]) -> None:
    """
    Insert multiple winning distributions into the database.
    """
    if distributions:
        await collection.insert_many([distribution.model_dump() for distribution in distributions])

async def get_winning_distributions_by_date_range(
    collection: AsyncIOMotorCollection,
    current_user: UserInDB,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    phone: Optional[str] = None,
) -> List[WinningDistributionInDB]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start = start_date or today
    query_end = end_date or default_end
    
    phone = "system" if current_user.role == "system" else current_user.phone 
    
    cursor = collection.find({
        "phone": phone,
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

# async def get_winning_summary(collection: AsyncIOMotorCollection):
#     now = datetime.now()
#     today = now.replace(hour=0, minute=0, second=0, microsecond=0)

#     start_of_week = today - timedelta(days=today.weekday())
#     start_of_month = today.replace(day=1)
#     start_of_year = today.replace(month=1, day=1)

#     match_stage = {
#         "$match": {
#             "date": { "$gte": start_of_year }
#         }
#     }

#     project_stage = {
#         "$project": {
#             "amount": 1,
#             "date": 1,
#             "day": { "$dateToString": { "format": "%Y-%m-%d", "date": "$date" } },
#             "week": { "$isoWeek": "$date" },
#             "month": { "$month": "$date" },
#             "year": { "$year": "$date" }
#         }
#     }

#     group_stage = {
#         "$group": {
#             "_id": None,
#             "dailyWinning": {
#                 "$sum": {
#                     "$cond": [{ "$eq": ["$day", today.strftime("%Y-%m-%d")] }, "$amount", 0]
#                 }
#             },
#             "weeklyWinning": {
#                 "$sum": {
#                     "$cond": [
#                         {
#                             "$and": [
#                                 { "$gte": ["$date", start_of_week] },
#                                 { "$lte": ["$date", now] }
#                             ]
#                         },
#                         "$amount",
#                         0
#                     ]
#                 }
#             },
#             "monthlyWinning": {
#                 "$sum": {
#                     "$cond": [
#                         {
#                             "$and": [
#                                 { "$gte": ["$date", start_of_month] },
#                                 { "$lte": ["$date", now] }
#                             ]
#                         },
#                         "$amount",
#                         0
#                     ]
#                 }
#             },
#             "yearToDateWinning": {
#                 "$sum": "$amount"
#             }
#         }
#     }

#     pipeline = [match_stage, project_stage, group_stage]

#     result = await collection.aggregate(pipeline).to_list(length=1)
#     return result[0] if result else {
#         "dailyWinning": 0,
#         "weeklyWinning": 0,
#         "monthlyWinning": 0,
#         "yearToDateWinning": 0
#     }


async def get_distribution_summary_by_phone(
    collection: AsyncIOMotorCollection,
    current_user: UserInDB,
) -> Dict[str, float]:
    now = datetime.now()

    # Date boundaries
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = start_of_today - timedelta(days=start_of_today.weekday())
    start_of_month = start_of_today.replace(day=1)
    start_of_year = start_of_today.replace(month=1, day=1)

    # Aggregate data for different ranges
    summaries = []
    ranges = [
        ("Today", start_of_today),
        ("Week To Date", start_of_week),
        ("Month To Date", start_of_month),
        ("Year To Date", start_of_year),
    ]

    phone = "system" if current_user.role == "system" else current_user.phone 

    for title, start_date in ranges:
        total = await collection.aggregate([
            {
                "$match": {
                    "phone": phone,
                    "date": {"$gte": start_date, "$lte": now}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "amount": {"$sum": "$amount"}
                }
            }
        ]).to_list(length=1)

        amount = total[0]["amount"] if total else 0
        summaries.append({"title": title, "amount": round(amount, 2)})

    return {
        "today": summaries[0]["amount"],
        "weekToDate": summaries[1]["amount"],
        "monthToDate": summaries[2]["amount"],
        "yearToDate": summaries[3]["amount"]
    }
async def approvDistributions(collection: AsyncIOMotorCollection,current_user: UserInDB, game_id:str):
    print(game_id)
    result = await collection.update_many(
        {"gameId": game_id},
        {
            "$set": 
                {"approved": True,"approvedBy": current_user.phone,"approvedDate": datetime.now()}
        }
    )
    print (f"Updated {result.modified_count} documents")
    return result.modified_count > 0