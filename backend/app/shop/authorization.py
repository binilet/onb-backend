"""Centralized role checks and Mongo scope filters for the shop hierarchy."""

from typing import Any

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.user import UserInDB


SYSTEM = "system"
AGENT = "agent"
ADMIN = "admin"
CASHIER = "cashier"
HIERARCHY_STAFF_ROLES = frozenset({SYSTEM, AGENT, ADMIN, CASHIER})


def require_roles(current_user: UserInDB, *allowed_roles: str) -> None:
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


def require_system(current_user: UserInDB) -> None:
    require_roles(current_user, SYSTEM)


async def shop_scope_filter(db: AsyncIOMotorDatabase, current_user: UserInDB) -> dict[str, Any]:
    """Return the mandatory Shop query filter for this staff member."""
    if current_user.role == SYSTEM:
        return {}
    if current_user.role == AGENT:
        return {"agentId": current_user.phone}
    if current_user.role in {ADMIN, CASHIER} and current_user.shopId:
        return {"shop_id": current_user.shopId}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No shop scope assigned")


async def branch_scope_filter(db: AsyncIOMotorDatabase, current_user: UserInDB) -> dict[str, Any]:
    """Return the mandatory ShopBranch query filter for this staff member."""
    if current_user.role == SYSTEM:
        return {}
    if current_user.role == AGENT:
        shops = await db.shops.find({"agentId": current_user.phone}, {"shop_id": 1}).to_list(length=None)
        return {"shopId": {"$in": [shop["shop_id"] for shop in shops]}}
    if current_user.role == ADMIN and current_user.shopId:
        return {"shopId": current_user.shopId}
    if current_user.role == CASHIER and current_user.branchId:
        return {"branch_id": current_user.branchId}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No branch scope assigned")


async def staff_scope_filter(db: AsyncIOMotorDatabase, current_user: UserInDB) -> dict[str, Any]:
    """Return the mandatory staff-only User query filter for hierarchy reads.

    Plain registered players (role ``user``/null) are intentionally excluded:
    they are not shop-hierarchy staff and have no shop assignment in the MVP.
    """
    if current_user.role == SYSTEM:
        return {"role": {"$in": list(HIERARCHY_STAFF_ROLES)}}
    if current_user.role == AGENT:
        shops = await db.shops.find({"agentId": current_user.phone}, {"shop_id": 1}).to_list(length=None)
        return {"shopId": {"$in": [shop["shop_id"] for shop in shops]}, "role": {"$in": [ADMIN, CASHIER]}}
    if current_user.role == ADMIN and current_user.shopId:
        return {"shopId": current_user.shopId, "role": CASHIER}
    if current_user.role == CASHIER:
        return {"phone": current_user.phone}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No staff scope assigned")


async def get_scoped_shop(db: AsyncIOMotorDatabase, current_user: UserInDB, shop_id: str) -> dict:
    scope = await shop_scope_filter(db, current_user)
    shop = await db.shops.find_one({**scope, "shop_id": shop_id})
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return shop


async def get_scoped_branch(db: AsyncIOMotorDatabase, current_user: UserInDB, branch_id: str) -> dict:
    scope = await branch_scope_filter(db, current_user)
    branch = await db.shopBranches.find_one({**scope, "branch_id": branch_id})
    if branch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop branch not found")
    return branch


async def get_scoped_staff_user(db: AsyncIOMotorDatabase, current_user: UserInDB, phone: str) -> dict:
    if current_user.role == SYSTEM:
        user = await db.users.find_one({"phone": phone})
    else:
        scope = await staff_scope_filter(db, current_user)
        user = await db.users.find_one({**scope, "phone": phone})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff user not found")
    return user


async def validate_staff_creation(
    db: AsyncIOMotorDatabase,
    current_user: UserInDB,
    role: str,
    shop_id: str | None,
    branch_id: str | None,
) -> None:
    """Validate reporting-line and shop/branch constraints before staff creation."""
    if role == AGENT:
        require_system(current_user)
        if shop_id is not None or branch_id is not None:
            raise HTTPException(status_code=422, detail="Agents must not be single-shop or branch scoped")
        return

    if role not in {ADMIN, CASHIER}:
        raise HTTPException(status_code=422, detail="Only agent, admin, and cashier staff roles can be created here")
    if not shop_id:
        raise HTTPException(status_code=422, detail="Admin and cashier staff require shopId")
    shop = await get_scoped_shop(db, current_user, shop_id)

    if current_user.role not in {SYSTEM, AGENT, ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create staff")
    if current_user.role == ADMIN and role != CASHIER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins may create cashiers only")

    if role == ADMIN:
        if branch_id is not None:
            raise HTTPException(status_code=422, detail="Admins must not be branch scoped")
        existing_admin = await db.users.find_one({"role": ADMIN, "shopId": shop["shop_id"]})
        if existing_admin is not None:
            raise HTTPException(status_code=409, detail="This shop already has an admin")
        return

    if not branch_id:
        raise HTTPException(status_code=422, detail="Cashiers require branchId")
    branch = await db.shopBranches.find_one({"branch_id": branch_id, "shopId": shop["shop_id"]})
    if branch is None:
        raise HTTPException(status_code=422, detail="branchId must belong to shopId")
