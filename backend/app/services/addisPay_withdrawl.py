from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorCollection
from datetime import datetime, timedelta
from schemas.addispay.addisPayWithdrawRequest import AddisPayWithdrawalRequest
from schemas.addispay.addisPayWithdrawResponse import AddisPayWithdrawalResponse
from schemas.addispay.addisPayWithdrawCallback import AddisPayWithdrawalCallback

async def get_addispay_withdraw_request_by_date_range(
    deposits_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[AddisPayWithdrawalRequest]:
    # Set default to today (midnight to 23:59:59) if dates are not provided
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)  # 23:59:59

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    print(f"Querying deposits from {query_start_date} to {query_end_date}")
    cursor = deposits_collection.find({
        "createdAt": {"$gte": query_start_date, "$lte": query_end_date}
    })
    deposits = await cursor.to_list()
    return [AddisPayWithdrawalRequest(**deposit) for deposit in deposits]

async def get_addispay_withdraw_callback_by_date_range(
    callbacks_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[AddisPayWithdrawalCallback]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = callbacks_collection.find({
        "createdAt": {"$gte": query_start_date, "$lte": query_end_date}
    })
    callbacks = await cursor.to_list()
    return [AddisPayWithdrawalCallback(**callback) for callback in callbacks]

async def get_addispay_withdraw_response_by_date_range(
    callbacks_collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[AddisPayWithdrawalResponse]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    default_end = today + timedelta(days=1) - timedelta(seconds=1)

    query_start_date = start_date if start_date is not None else today
    query_end_date = end_date if end_date is not None else default_end

    cursor = callbacks_collection.find({
        "createdAt": {"$gte": query_start_date, "$lte": query_end_date}
    })
    callbacks = await cursor.to_list()
    return [AddisPayWithdrawalResponse(**callback) for callback in callbacks]