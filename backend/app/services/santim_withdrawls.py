from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from datetime import datetime, timedelta
from schemas.santimWithdrawls import SantimWithdrawlRequestInDB, SantimWithdrawlStatusInDB

async def get_santim_withdrawal_requests_by_date_range(
    withdrawals_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 10
) -> List[SantimWithdrawlRequestInDB]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = withdrawals_collection.find({
        "createdAt": {"$gte": query_start_date, "$lte": query_end_date}
    }).skip(skip).limit(limit)
    withdrawals = await cursor.to_list(length=limit)
    return [SantimWithdrawlRequestInDB(**withdrawal) for withdrawal in withdrawals]

async def get_santim_withdrawal_statuses_by_date_range(
    statuses_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 10
) -> List[SantimWithdrawlStatusInDB]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = statuses_collection.find({
        "created_at": {"$gte": query_start_date, "$lte": query_end_date}
    }).skip(skip).limit(limit)
    statuses = await cursor.to_list(length=limit)
    return [SantimWithdrawlStatusInDB(**status) for status in statuses]