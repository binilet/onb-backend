from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder

from models.user import UserInDB
from shop.authorization import ADMIN, AGENT, CASHIER, SUBAGENT, SYSTEM, shop_scope_filter


class ShopActionLog(BaseModel):
    log_id: str = Field(default_factory=lambda: str(uuid4()))
    actorPhone: str
    actorRole: str
    actionType: str
    entityType: str
    entityId: str
    shopId: Optional[str] = None
    branchId: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


async def write_action_log(
    db: AsyncIOMotorDatabase,
    actor: UserInDB,
    action_type: str,
    entity_type: str,
    entity_id: str,
    *,
    shop_id: Optional[str] = None,
    branch_id: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> ShopActionLog:
    log = ShopActionLog(
        actorPhone=actor.phone,
        actorRole=actor.role or "unknown",
        actionType=action_type,
        entityType=entity_type,
        entityId=entity_id,
        shopId=shop_id,
        branchId=branch_id,
        detail=jsonable_encoder(detail or {}),
    )
    await db.shopActionLogs.insert_one(log.model_dump())
    return log


async def list_scoped_action_logs(
    db: AsyncIOMotorDatabase,
    current_user: UserInDB,
    log_date: date,
    shop_id: Optional[str] = None,
) -> list[ShopActionLog]:
    if current_user.role == SYSTEM:
        query = {"shopId": shop_id} if shop_id else {}
    elif current_user.role in {AGENT, SUBAGENT}:
        shops = await db.shops.find(await shop_scope_filter(db, current_user), {"shop_id": 1}).to_list(length=None)
        query = {"$or": [{"shopId": {"$in": [shop["shop_id"] for shop in shops]}}, {"actorPhone": current_user.phone}]}
    elif current_user.role == ADMIN and current_user.shopId:
        query = {"$or": [{"shopId": current_user.shopId}, {"actorPhone": current_user.phone}]}
    elif current_user.role == CASHIER and current_user.branchId:
        query = {"$or": [{"branchId": current_user.branchId}, {"actorPhone": current_user.phone}]}
    else:
        query = {"_id": None}
    if shop_id and current_user.role != SYSTEM:
        query = {"$and": [query, {"shopId": shop_id}]}
    start_at = datetime.combine(log_date, time.min, tzinfo=timezone(timedelta(hours=3)))
    end_at = start_at + timedelta(days=1)
    query = {"$and": [query, {"createdAt": {"$gte": start_at, "$lt": end_at}}]} if query else {"createdAt": {"$gte": start_at, "$lt": end_at}}
    documents = await db.shopActionLogs.find(query).sort("createdAt", -1).to_list(length=None)
    return [ShopActionLog(**document) for document in documents]
