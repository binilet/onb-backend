from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from models.user import UserInDB
from shop.authorization import SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER, shop_scope_filter

class PlayerRoomWithdrawal(BaseModel):
    id: str; withdrawalId: str; playerPhone: str; shopId: str; branchId: str; amount: Decimal; status: str
    receiverPhone: str | None = None; receiverConfirmedAt: datetime | None = None; receiverConfirmedByPhone: str | None = None; playerConfirmedAt: datetime | None = None; createdAt: datetime

def view(item):
    item = item.copy(); item['id'] = str(item.pop('_id')); item['amount'] = item['amount'].to_decimal() if isinstance(item['amount'], Decimal128) else Decimal(str(item['amount'])); return PlayerRoomWithdrawal(**item)

async def list_withdrawals(db: AsyncIOMotorDatabase, user: UserInDB, status_value: str = 'PENDING', start_at=None, end_at=None):
    if user.role == SYSTEM: scope = {}
    elif user.role in {AGENT, SUBAGENT}:
        shops = await db.shops.find(await shop_scope_filter(db, user), {'shop_id': 1}).to_list(None); scope = {'shopId': {'$in': [x['shop_id'] for x in shops]}}
    elif user.role == ADMIN and user.shopId: scope = {'shopId': user.shopId}
    elif user.role == CASHIER and user.branchId: scope = {'$or': [{'branchId': user.branchId}, {'receiverPhone': user.phone}]}
    else: raise HTTPException(403, 'No withdrawal scope assigned')
    query = {**scope, 'status': status_value}
    if start_at or end_at: query['createdAt'] = {**({'$gte': start_at} if start_at else {}), **({'$lt': end_at} if end_at else {})}
    return [view(x) for x in await db.shopWithdrawals.find(query).sort('createdAt', -1).to_list(250)]

async def receiver_confirm(db: AsyncIOMotorDatabase, user: UserInDB, withdrawal_id: str):
    item = await db.shopWithdrawals.find_one({'withdrawalId': withdrawal_id})
    if not item: raise HTTPException(404, 'Withdrawal request not found')
    if user.role == CASHIER and item['branchId'] != user.branchId and item.get('receiverPhone') != user.phone: raise HTTPException(403, 'Outside cashier withdrawal scope')
    if item['status'] in {'SETTLED','DECLINED','CANCELLED'}: return view(item)
    now = datetime.now(timezone.utc)
    if not item.get('playerConfirmedAt'):
        await db.shopWithdrawals.update_one({'_id': item['_id']}, {'$set': {'status': 'CASH_DISBURSED', 'receiverConfirmedAt': now, 'receiverConfirmedByPhone': user.phone}})
        return view((await db.shopWithdrawals.find_one({'_id': item['_id']})))
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            changed = await db.shopWithdrawals.update_one({'_id': item['_id'], 'status': {'$in': ['PENDING','CASH_DISBURSED','PLAYER_CONFIRMED']}}, {'$set': {'status':'SETTLED','receiverConfirmedAt':now,'receiverConfirmedByPhone':user.phone,'ledgerId':f"shop-withdrawal:{item['withdrawalId']}"}}, session=session)
            if changed.modified_count:
                amount = item['amount'] if isinstance(item['amount'], Decimal128) else Decimal128(Decimal(str(item['amount'])))
                debit = await db.playerRoomWallets.update_one({'playerPhone':item['playerPhone'],'shopId':item['shopId'],'currentBalance':{'$gte':amount}}, {'$inc':{'currentBalance':Decimal128(-amount.to_decimal())}, '$set':{'updatedAt':now}}, session=session)
                if not debit.matched_count: raise HTTPException(409, 'Wallet balance changed before settlement')
                await db.playerRoomWalletLedgers.insert_one({'ledger_id':str(uuid4()),'playerPhone':item['playerPhone'],'shopId':item['shopId'],'branchId':item['branchId'],'amount':Decimal128(-amount.to_decimal()),'reason':'WITHDRAWAL','toppedUpByPhone':user.phone,'idempotencyKey':f"shop-withdrawal:{item['withdrawalId']}",'createdAt':now}, session=session)
    return view((await db.shopWithdrawals.find_one({'_id': item['_id']})))
