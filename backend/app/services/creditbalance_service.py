from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from datetime import datetime, timedelta
from schemas.creditBalance import CreditBalanceInDB

async def get_credit_balances_by_date_range(
    balances_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = 10
) -> List[CreditBalanceInDB]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = balances_collection.find({
        "created_at": {"$gte": query_start_date, "$lte": query_end_date}
    }).skip(skip).limit(limit)
    balances = await cursor.to_list(length=limit)
    return [CreditBalanceInDB(**balance) for balance in balances]