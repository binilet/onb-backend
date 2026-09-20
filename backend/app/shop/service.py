from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from shop.schemas import Shop, ShopBranch, ShopBranchCreate, ShopBranchUpdate, ShopCreate, ShopUpdate


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_shop(db: AsyncIOMotorDatabase, payload: ShopCreate) -> Shop:
    shop = Shop(**payload.model_dump())
    await db.shops.insert_one(shop.model_dump())
    return shop


async def list_shops(db: AsyncIOMotorDatabase, agent_phone: Optional[str] = None) -> list[Shop]:
    query = {"agentId": agent_phone} if agent_phone is not None else {}
    documents = await db.shops.find(query).to_list(length=None)
    return [Shop(**document) for document in documents]


async def get_shop(db: AsyncIOMotorDatabase, shop_id: str) -> Optional[Shop]:
    document = await db.shops.find_one({"shop_id": shop_id})
    return Shop(**document) if document else None


async def update_shop(db: AsyncIOMotorDatabase, shop_id: str, payload: ShopUpdate) -> Optional[Shop]:
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updatedAt"] = utc_now()
        await db.shops.update_one({"shop_id": shop_id}, {"$set": changes})
    return await get_shop(db, shop_id)


async def delete_shop(db: AsyncIOMotorDatabase, shop_id: str) -> bool:
    result = await db.shops.delete_one({"shop_id": shop_id})
    return result.deleted_count == 1


async def create_branch(db: AsyncIOMotorDatabase, shop_id: str, payload: ShopBranchCreate) -> ShopBranch:
    branch = ShopBranch(shopId=shop_id, **payload.model_dump())
    await db.shopBranches.insert_one(branch.model_dump())
    return branch


async def list_branches(db: AsyncIOMotorDatabase, shop_id: Optional[str] = None) -> list[ShopBranch]:
    query = {"shopId": shop_id} if shop_id is not None else {}
    documents = await db.shopBranches.find(query).to_list(length=None)
    return [ShopBranch(**document) for document in documents]


async def get_branch(db: AsyncIOMotorDatabase, branch_id: str) -> Optional[ShopBranch]:
    document = await db.shopBranches.find_one({"branch_id": branch_id})
    return ShopBranch(**document) if document else None


async def update_branch(
    db: AsyncIOMotorDatabase, branch_id: str, payload: ShopBranchUpdate
) -> Optional[ShopBranch]:
    changes = payload.model_dump(exclude_unset=True)
    if changes:
        changes["updatedAt"] = utc_now()
        await db.shopBranches.update_one({"branch_id": branch_id}, {"$set": changes})
    return await get_branch(db, branch_id)


async def delete_branch(db: AsyncIOMotorDatabase, branch_id: str) -> bool:
    result = await db.shopBranches.delete_one({"branch_id": branch_id})
    return result.deleted_count == 1
