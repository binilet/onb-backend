from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from datetime import datetime, timedelta
from schemas.santimDepositRequest import SantimDepositRequestInDB
from schemas.santimDepositStatus import SantimDepositStatusInDB


async def get_santim_deposits_by_date_range(
    deposits_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000
) -> List[SantimDepositRequestInDB]:
    # Set default to today (midnight to 23:59:59) if dates are not provided
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)  # 23:59:59

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = deposits_collection.find({
        "createdAt": {"$gte": query_start_date, "$lte": query_end_date}
    }).skip(skip).limit(limit)
    deposits = await cursor.to_list(length=limit)
    return [SantimDepositRequestInDB(**deposit) for deposit in deposits]

async def get_santim_deposit_statuses_by_date_range(
    statuses_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 1000
) -> List[SantimDepositStatusInDB]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = statuses_collection.find({
        "created_at": {"$gte": query_start_date, "$lte": query_end_date}
    }).skip(skip).limit(limit)
    statuses = await cursor.to_list(length=limit)
    return [SantimDepositStatusInDB(**status) for status in statuses]