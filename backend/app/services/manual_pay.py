from fastapi import Depends
from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorCollection,AsyncIOMotorClient,AsyncIOMotorDatabase
from bson import ObjectId
from schemas.manualPay.manual_deposit import ManualDepositRequest
from schemas.manualPay.manual_request import ManualWithRequest
from fastapi import HTTPException, status
from core.config import settings
from core.db import get_db,get_client
from datetime import datetime,timedelta
from models.user import UserInDB

async def fetch_manual_deposits(
    collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    phone: Optional[str] = None,
    processed: Optional[bool] = None
) -> List[ManualDepositRequest]:
    
    query = {}

    if start_date and end_date:
        # Extend end_date to end of the day
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["createdAt"] = {"$gte": start_date, "$lte": end_date}
    elif start_date:
        query["createdAt"] = {"$gte": start_date}
    elif end_date:
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["createdAt"] = {"$lte": end_date}

    if phone:
        query["phone"] = phone

    if processed is not None:
        query["processed"] = processed


    cursor = collection.find(query).sort("createdAt", -1)
    results = []  
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(ManualDepositRequest(**doc))
    
    return results

# async def approve_manual_deposit(
#     collection: AsyncIOMotorCollection,
#     deposit_id: str
# ) -> bool:
#     if not ObjectId.is_valid(deposit_id):
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid deposit ID."
#         )

#     # update user balance;
    
#     # create transaction history;

#     result = await collection.update_one(
#         {"_id": ObjectId(deposit_id)},
#         {"$set": {"processed": True}}
#     )

#     if result.matched_count == 0:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Manual deposit not found."
#         )

#     return result.modified_count > 0
async def approve_manual_deposit(
    client: AsyncIOMotorClient,
    deposit_collection: AsyncIOMotorCollection,
    credit_collection: AsyncIOMotorCollection,
    trx_history_collection: AsyncIOMotorCollection,
    deposit_id: str
) -> bool:
    try:
        if not ObjectId.is_valid(deposit_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid deposit ID."
            )
        session = await client.start_session()
        async with session.start_transaction():
        # 1. Find deposit
        
            deposit_doc = await deposit_collection.find_one(
                {"_id": ObjectId(deposit_id), "processed": False},
                session=session
            )

            if deposit_doc:
                deposit_doc["_id"] = str(deposit_doc["_id"])
                deposit = ManualDepositRequest(**deposit_doc)
            else:
                deposit = None
            
            if not deposit:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Manual deposit not found or already processed."
                )

            phone = deposit.phone # deposit["phone"]
            amount = deposit.amount #deposit["amount"]
            trxId = deposit.trxId #deposit["trxId"]

            # 2. Update user's balance
            user_result = await credit_collection.update_one(
                {"phone": phone},
                [
                    { "$set": { "previous_balance": "$current_balance" } },
                    { "$set": { "current_balance": { "$add": ["$current_balance", amount] } } }
                ],
                session=session
            )
            print("User update result:", user_result)
            if user_result.matched_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found."
                )

            # 3. Mark deposit as processed
            await deposit_collection.update_one(
                {"_id": ObjectId(deposit_id)},
                {"$set": {"processed": True, "processed_at": datetime.now(), "processingMsg":f'dear {phone}, {amount} birr has successfully deposited to your account.',"status":'SUCCESS'}},
                session=session
            )

            # 4. Create transaction history
            transaction = {
                "phone": phone,
                "date": datetime.now(),
                "amount": amount,
                "type": "deposit",
                "message": "Manual deposit approved",
                "isdebit": True,
                "reference": str(deposit_id),
                "remark": "Manual deposit approval",
                "transaction_ref": f"{trxId}",  # custom reference
                "game_id": None,
            }
            await trx_history_collection.insert_one(transaction, session=session)
            print("Transaction history created:", transaction)
        return True
    except HTTPException as e:
        msg:str = str(e)
        await deposit_collection.update_one(
                {"_id": ObjectId(deposit_id)},
                {"$set": {"processed": True, "processed_at": datetime.now(), "processingMsg":f'{msg}',"status":"FAILED"}}
            )
        raise e
    finally:
        await session.end_session()


# listen to changes in manual deposit collection and perform payment validations
async def watch_deposit_inserts(db: AsyncIOMotorDatabase, client: AsyncIOMotorClient):
    deposit_collection = db["manualdepositrequests"]
    print('********************* watch kicked *********************')
    pipeline = [
        {
            "$match": {
                "$or": [
                    {
                        "operationType": "insert",
                        "fullDocument.isVerified": True
                    },
                    {
                        "operationType": "update",
                        "updateDescription.updatedFields.isVerified": True
                    }
                ]
            }
        }
    ]

    async with deposit_collection.watch(pipeline, full_document="updateLookup") as stream:
        async for change in stream:
            doc = change.get("fullDocument")
            if not doc:
                continue  # Defensive: skip if fullDocument isn't populated

            print(f"[CHANGE STREAM] Verified deposit: {doc}")

            await approve_manual_deposit(
                client,
                deposit_collection,
                db["creditbalances"],
                db["transactionhistories"],
                str(doc["_id"])
            )

#handling of manual withdrawl requests
async def getManualWithdrawRequests(    
    collection: AsyncIOMotorCollection,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    phone: Optional[str] = None,
    approved: Optional[bool] = None
) -> List[ManualWithRequest]:
    
    query = {}

    print(start_date)
    print(end_date)

    if start_date and end_date:
        # Extend end_date to end of the day
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=999998)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["createdAt"] = {"$gte": start_date, "$lte": end_date}
    elif start_date and not end_date:
        
        end_date = start_date
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=999998)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        query["createdAt"] = {"$gte": start_date, "$lte": end_date}
    elif end_date and not start_date:
        start_date = end_date
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=999998)
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["createdAt"] = {"$gte": start_date, "$lte": end_date}

    if phone:
        query["phone"] = phone

    if approved is not None:
        query["approved"] = approved

    print(query)


    cursor = collection.find(query).sort("createdAt", -1)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(ManualWithRequest(**doc))
    
    return results


async def approve_manual_withdraw_request(
    client: AsyncIOMotorClient,
    withdrawCollection: AsyncIOMotorCollection,
    creditCollection: AsyncIOMotorCollection,
    trxHistoryCollection: AsyncIOMotorCollection,
    current_user: UserInDB,
    withdrawId: str,
    reference: str
) -> bool:

    if not ObjectId.is_valid(withdrawId):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid withdraw request ID."
        )

    session = await client.start_session()
    try:
        async with session.start_transaction():
            # Step 1: Fetch withdraw request
            with_doc = await withdrawCollection.find_one(
                {"_id": ObjectId(withdrawId), "approved": False},
                session=session
            )

            if not with_doc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Withdraw request not found or already approved."
                )

            withdraw = ManualWithRequest(**{**with_doc, "_id": str(with_doc["_id"])})
            phone, amount = withdraw.phone, withdraw.amount

            # Step 2: Deduct credit if sufficient
            credit_result = await creditCollection.update_one(
                {"phone": phone, "current_balance": {"$gte": amount}},
                [
                    {"$set": {"previous_balance": "$current_balance"}},
                    {"$set": {"current_balance": {"$subtract": ["$current_balance", amount]}}}
                ],
                session=session
            )

            if credit_result.matched_count == 0:
                user_exists = await creditCollection.find_one({"phone": phone})
                if not user_exists:
                    raise HTTPException(status_code=404, detail="Credit record not found.")
                raise HTTPException(status_code=400, detail="Insufficient balance.")

            # Step 3: Approve the withdraw
            await withdrawCollection.update_one(
                {"_id": ObjectId(withdrawId)},
                {"$set": {
                    "approved": True,
                    "approvedBy": current_user.username,
                    "reference": reference
                }},
                session=session
            )

            # Step 4: Create transaction history
            transaction = {
                "phone": phone,
                "date": datetime.now(),
                "amount": amount,
                "type": "withdraw",
                "message": "Manual withdraw approved",
                "isdebit": False,
                "reference": str(withdrawId),
                "remark": "Manual Request approval",
                "transaction_ref": reference,
                "game_id": None
            }

            await trxHistoryCollection.insert_one(transaction, session=session)
            return True
    except Exception as e:
        await session.abort_transaction()
        raise e  # re-raise the original exception

    finally:
        await session.end_session()


