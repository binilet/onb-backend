from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Literal, Optional
from uuid import uuid4

from bson.decimal128 import Decimal128
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from models.user import UserInDB
from shop.authorization import ADMIN, AGENT, CASHIER, SUBAGENT, SYSTEM, shop_scope_filter
from shop.player_room_wallet_service import _validate_room_scope, ensure_player_room_wallet_indexes


class PlayerRoomDeposit(BaseModel):
    # `_from_document` deliberately converts Mongo's `_id` to `id` so the
    # browser receives the same field it uses in the decision URL.
    id: str
    jobId: str
    playerPhone: str
    shopId: str
    branchId: str
    amount: Decimal
    depositMethod: Literal["TELEBIRR", "CASH"] = "TELEBIRR"
    recipientPhone: Optional[str] = None
    recipientAccountName: Optional[str] = None
    transactionId: Optional[str] = None
    status: str
    createdAt: datetime
    reviewedByPhone: Optional[str] = None
    reviewedAt: Optional[datetime] = None
    reviewNote: Optional[str] = None

class PlayerRoomDepositDecision(BaseModel):
    action: Literal["APPROVE", "DECLINE", "VOID"]
    note: Optional[str] = Field(default=None, max_length=500)


def _from_document(document: dict) -> PlayerRoomDeposit:
    data = document.copy()
    data["id"] = str(data.pop("_id"))
    data["amount"] = data["amount"].to_decimal() if isinstance(data["amount"], Decimal128) else Decimal(str(data["amount"]))
    return PlayerRoomDeposit(**data)


async def list_player_room_deposits(
    db: AsyncIOMotorDatabase,
    current_user: UserInDB,
    status_value: str = "PENDING",
    deposit_method: Optional[str] = None,
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
) -> list[PlayerRoomDeposit]:
    if current_user.role not in {SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER}:
        raise HTTPException(status_code=403, detail="Only shop staff may review room-wallet deposits")
    if current_user.role == SYSTEM:
        scope = {}
    elif current_user.role in {AGENT, SUBAGENT}:
        shops = await db.shops.find(await shop_scope_filter(db, current_user), {"shop_id": 1}).to_list(length=None)
        scope = {"shopId": {"$in": [shop["shop_id"] for shop in shops]}}
    elif current_user.role == ADMIN and current_user.shopId:
        scope = {"shopId": current_user.shopId}
    elif current_user.role == CASHIER and current_user.branchId:
        # A branch cashier can process its branch queue. Matching the recipient
        # phone as well supports branches whose registered payment phone is the
        # cashier's own login number.
        scope = {"$or": [{"branchId": current_user.branchId}, {"recipientPhone": current_user.phone}]}
    else:
        raise HTTPException(status_code=403, detail="No deposit-review scope assigned")

    query = {**scope, "status": status_value.upper()}
    if deposit_method:
        query["depositMethod"] = deposit_method.upper()
    if start_at or end_at:
        query["createdAt"] = {**({"$gte": start_at} if start_at else {}), **({"$lt": end_at} if end_at else {})}
    documents = await db.shopDeposits.find(query).sort("createdAt", -1).to_list(length=250)
    return [_from_document(document) for document in documents]


async def decide_player_room_deposit(db: AsyncIOMotorDatabase, current_user: UserInDB, deposit_id: str, decision: PlayerRoomDepositDecision) -> PlayerRoomDeposit:
    from bson import ObjectId
    if current_user.role not in {SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER}:
        raise HTTPException(status_code=403, detail="Only shop staff may review room-wallet deposits")
    try:
        object_id = ObjectId(deposit_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Deposit request not found") from exc
    deposit = await db.shopDeposits.find_one({"_id": object_id})
    if deposit is None:
        raise HTTPException(status_code=404, detail="Deposit request not found")
    await _validate_room_scope(db, current_user, deposit["shopId"], deposit["branchId"])
    if current_user.role == CASHIER and deposit["branchId"] != current_user.branchId and deposit.get("recipientPhone") != current_user.phone:
        raise HTTPException(status_code=403, detail="Cashiers may review only their own branch deposits")
    if deposit.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail="This deposit request has already been reviewed")
    now = datetime.now(timezone.utc)
    next_status = {"APPROVE": "APPROVED", "DECLINE": "DECLINED", "VOID": "VOIDED"}[decision.action]
    await ensure_player_room_wallet_indexes(db)
    async with await db.client.start_session() as session:
        async with session.start_transaction():
            changed = await db.shopDeposits.update_one({"_id": object_id, "status": "PENDING"}, {"$set": {"status": next_status, "reviewedByPhone": current_user.phone, "reviewedAt": now, "reviewNote": decision.note}}, session=session)
            if changed.modified_count != 1:
                raise HTTPException(status_code=409, detail="Deposit request was already reviewed")
            if decision.action == "APPROVE":
                amount = deposit["amount"] if isinstance(deposit["amount"], Decimal128) else Decimal128(Decimal(str(deposit["amount"])))
                await db.playerRoomWallets.update_one({"playerPhone": deposit["playerPhone"], "shopId": deposit["shopId"]}, {"$setOnInsert": {"playerPhone": deposit["playerPhone"], "shopId": deposit["shopId"], "branchId": deposit["branchId"], "isWithdrawable": True}, "$inc": {"currentBalance": amount}, "$set": {"updatedAt": now}}, upsert=True, session=session)
                await db.playerRoomWalletLedgers.insert_one({"ledger_id": str(uuid4()), "playerPhone": deposit["playerPhone"], "shopId": deposit["shopId"], "branchId": deposit["branchId"], "amount": amount, "reason": "DEPOSIT", "toppedUpByPhone": current_user.phone, "idempotencyKey": f"shop-deposit:{deposit['jobId']}", "createdAt": now}, session=session)
    updated = await db.shopDeposits.find_one({"_id": object_id})
    return _from_document(updated)
