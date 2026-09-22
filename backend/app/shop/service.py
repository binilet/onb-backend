from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from shop.schemas import Shop, ShopBranch, ShopBranchCreate, ShopBranchUpdate, ShopCreate, ShopUpdate


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_shop(db: AsyncIOMotorDatabase, payload: ShopCreate) -> Shop:
    representative = await db.users.find_one({"phone": payload.representativePhone, "role": {"$in": ["agent", "subagent", "admin"]}})
    if representative is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Select an agent, subagent, or admin as the Shop representative")
    shop = Shop(
        **payload.model_dump(),
        representativeRole=representative["role"],
        agentId=payload.representativePhone,
    )
    await db.shops.insert_one(shop.model_dump())
    if representative["role"] == "admin":
        await db.users.update_one({"phone": representative["phone"]}, {"$set": {"shopId": shop.shop_id}})
    return shop


async def list_shops(db: AsyncIOMotorDatabase, representative_phones: Optional[list[str]] = None) -> list[Shop]:
    query = {"$or": [{"representativePhone": {"$in": representative_phones}}, {"agentId": {"$in": representative_phones}}]} if representative_phones is not None else {}
    documents = await db.shops.find(query).to_list(length=None)
    for document in documents:
        document.setdefault("representativePhone", document.get("agentId"))
        document.setdefault("representativeRole", "agent")
    return [Shop(**document) for document in documents]


async def get_shop(db: AsyncIOMotorDatabase, shop_id: str) -> Optional[Shop]:
    document = await db.shops.find_one({"shop_id": shop_id})
    if document:
        document.setdefault("representativePhone", document.get("agentId"))
        document.setdefault("representativeRole", "agent")
    return Shop(**document) if document else None


async def update_shop(db: AsyncIOMotorDatabase, shop_id: str, payload: ShopUpdate) -> Optional[Shop]:
    changes = payload.model_dump(exclude_unset=True)
    representative = None
    if "representativePhone" in changes:
        representative = await db.users.find_one({"phone": changes["representativePhone"], "role": {"$in": ["agent", "subagent", "admin"]}})
        if representative is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=422, detail="Select an agent, subagent, or admin as the Shop representative")
        changes["representativeRole"] = representative["role"]
        changes["agentId"] = representative["phone"]
    if changes:
        changes["updatedAt"] = utc_now()
        await db.shops.update_one({"shop_id": shop_id}, {"$set": changes})
        if representative and representative["role"] == "admin":
            await db.users.update_one({"phone": representative["phone"]}, {"$set": {"shopId": shop_id}})
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
