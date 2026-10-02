"""Centralized role checks and Mongo scope filters for the shop hierarchy."""

from typing import Any

from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.user import UserInDB


SYSTEM = "system"
AGENT = "agent"
SUBAGENT = "subagent"
ADMIN = "admin"
CASHIER = "cashier"
HIERARCHY_STAFF_ROLES = frozenset({SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER})


async def inherited_owner_assignment(
    db: AsyncIOMotorDatabase,
    current_user: UserInDB,
    child_role: str,
    owner_phone: str | None = None,
) -> dict[str, str | None]:
    """Return a consistent direct-parent and inherited hierarchy chain.

    ``parentPhone`` identifies who created/owns the account directly.  The
    agent, subagent, and admin fields are denormalized ancestry fields used by
    fast scoped reads.  They are always derived here, never accepted from a
    staff-creation request.
    """
    allowed_owner_roles = {
        AGENT: {SYSTEM},
        SUBAGENT: {SYSTEM, AGENT},
        ADMIN: {SYSTEM, AGENT, SUBAGENT},
        CASHIER: {SYSTEM, AGENT, SUBAGENT, ADMIN},
        "user": {SYSTEM, AGENT, SUBAGENT, ADMIN},
    }
    if current_user.role == SYSTEM:
        # System is the implicit owner whenever no explicit owner is selected.
        if not owner_phone or owner_phone == current_user.phone:
            owner = current_user.model_dump()
        else:
            owner_query = {"phone": owner_phone}
            if child_role != "user":
                owner_query["forShop"] = True
            owner = await db.users.find_one(owner_query)
            if owner is None:
                raise HTTPException(status_code=422, detail="Selected owner is not an active shop staff account")
    else:
        if owner_phone and owner_phone != current_user.phone:
            raise HTTPException(status_code=403, detail="Staff can create accounts only under themselves")
        owner = current_user.model_dump()

    if owner.get("role") not in allowed_owner_roles.get(child_role, set()):
        raise HTTPException(status_code=422, detail=f"A {child_role} must be assigned to an eligible direct owner")

    owner_role = owner["role"]
    return {
        "parentPhone": owner["phone"],
        "agentId": owner["phone"] if owner_role == AGENT else owner.get("agentId"),
        "subagentId": owner["phone"] if owner_role == SUBAGENT else owner.get("subagentId"),
        "adminId": owner["phone"] if owner_role == ADMIN else owner.get("adminId"),
    }


def validate_assigned_cut(current_user: UserInDB, role: str, cut_percent: float | None) -> None:
    """Validate the direct parent's cut assignment without relying on the UI."""
    if current_user.role == ADMIN and role == CASHIER:
        if cut_percent not in (None, 100):
            raise HTTPException(status_code=422, detail="Admin-to-cashier transfers are always 1:1 (100%)")
        return
    # System has no assigned parent cut, so it is the root of the hierarchy.
    if current_user.role == SYSTEM:
        return
    if current_user.role not in {AGENT, SUBAGENT}:
        return
    if cut_percent is None:
        raise HTTPException(status_code=422, detail="A cut percentage is required for this staff assignment")
    parent_cut = float(current_user.parentCutPercent or 0)
    if cut_percent < parent_cut:
        raise HTTPException(status_code=422, detail="Assigned cut percentage cannot be lower than the assigner's cut percentage")


async def descendant_staff_phones(db: AsyncIOMotorDatabase, current_user: UserInDB) -> list[str]:
    """Return all direct and indirect staff descendants, including legacy reporting fields."""
    discovered: set[str] = set()
    frontier = [current_user.phone]
    while frontier:
        parents = frontier
        frontier = []
        documents = await db.users.find(
            {"$or": [
                {"parentPhone": {"$in": parents}},
                {"agentId": {"$in": parents}},
                {"adminId": {"$in": parents}},
            ], "forShop": True},
            {"phone": 1},
        ).to_list(length=None)
        for document in documents:
            phone = document.get("phone")
            if phone and phone not in discovered and phone != current_user.phone:
                discovered.add(phone)
                frontier.append(phone)
    return list(discovered)


def require_roles(current_user: UserInDB, *allowed_roles: str) -> None:
    if current_user.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")


def require_system(current_user: UserInDB) -> None:
    require_roles(current_user, SYSTEM)


async def shop_scope_filter(db: AsyncIOMotorDatabase, current_user: UserInDB) -> dict[str, Any]:
    """Return the mandatory Shop query filter for this staff member."""
    if current_user.role == SYSTEM:
        return {}
    if current_user.role in {AGENT, SUBAGENT}:
        phones = [current_user.phone, *(await descendant_staff_phones(db, current_user))]
        return {"$or": [{"representativePhone": {"$in": phones}}, {"agentId": {"$in": phones}}]}
    if current_user.role in {ADMIN, CASHIER} and current_user.shopId:
        return {"shop_id": current_user.shopId}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No shop scope assigned")


async def branch_scope_filter(db: AsyncIOMotorDatabase, current_user: UserInDB) -> dict[str, Any]:
    """Return the mandatory ShopBranch query filter for this staff member."""
    if current_user.role == SYSTEM:
        return {}
    if current_user.role in {AGENT, SUBAGENT}:
        shop_scope = await shop_scope_filter(db, current_user)
        shops = await db.shops.find(shop_scope, {"shop_id": 1}).to_list(length=None)
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
        return {"forShop": True}

    # Orphaned legacy staff can only be inspected and repaired by System.
    # Any populated hierarchy field represents an assigned owner while older
    # records are being migrated to the new complete ownership chain.
    has_assigned_owner = {
        "$or": [
            {"parentPhone": {"$exists": True, "$nin": [None, ""]}},
            {"agentId": {"$exists": True, "$nin": [None, ""]}},
            {"subagentId": {"$exists": True, "$nin": [None, ""]}},
            {"adminId": {"$exists": True, "$nin": [None, ""]}},
        ]
    }
    if current_user.role == AGENT:
        return {"$and": [{"agentId": current_user.phone, "forShop": True}, has_assigned_owner]}
    if current_user.role == SUBAGENT:
        return {"$and": [{"subagentId": current_user.phone, "forShop": True}, has_assigned_owner]}
    if current_user.role == ADMIN:
        return {"$and": [{"adminId": current_user.phone, "forShop": True}, has_assigned_owner]}
    if current_user.role == CASHIER:
        return {"$and": [{"phone": current_user.phone, "forShop": True}, has_assigned_owner]}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No staff scope assigned")


async def get_scoped_shop(db: AsyncIOMotorDatabase, current_user: UserInDB, shop_id: str) -> dict:
    scope = await shop_scope_filter(db, current_user)
    shop = await db.shops.find_one({**scope, "shop_id": shop_id})
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    shop.setdefault("representativePhone", shop.get("agentId"))
    shop.setdefault("representativeRole", "agent")
    return shop


async def get_scoped_branch(db: AsyncIOMotorDatabase, current_user: UserInDB, branch_id: str) -> dict:
    scope = await branch_scope_filter(db, current_user)
    branch = await db.shopBranches.find_one({**scope, "branch_id": branch_id})
    if branch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop branch not found")
    return branch


async def get_scoped_staff_user(db: AsyncIOMotorDatabase, current_user: UserInDB, phone: str) -> dict:
    if current_user.role == SYSTEM:
        user = await db.users.find_one({"phone": phone, "forShop": True})
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
    parent_cut_percent: float | None = None,
) -> None:
    """Validate reporting-line and shop/branch constraints before staff creation."""
    if role == AGENT:
        require_system(current_user)
        if shop_id is not None or branch_id is not None:
            raise HTTPException(status_code=422, detail="Agents must not be single-shop or branch scoped")
        validate_assigned_cut(current_user, role, parent_cut_percent)
        return

    if role == SUBAGENT:
        if current_user.role not in {SYSTEM, AGENT}:
            raise HTTPException(status_code=403, detail="Only system or agents may create subagents")
        if shop_id is not None or branch_id is not None:
            raise HTTPException(status_code=422, detail="Subagents must not be single-shop or branch scoped")
        validate_assigned_cut(current_user, role, parent_cut_percent)
        return

    if role not in {ADMIN, CASHIER}:
        raise HTTPException(status_code=422, detail="Only agent, subagent, admin, and cashier staff roles can be created here")

    if current_user.role not in {SYSTEM, AGENT, SUBAGENT, ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to create staff")
    if current_user.role == ADMIN and role != CASHIER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins may create cashiers only")

    if role == ADMIN:
        if branch_id is not None:
            raise HTTPException(status_code=422, detail="Admins must not be branch scoped")
        if shop_id:
            await get_scoped_shop(db, current_user, shop_id)
        validate_assigned_cut(current_user, role, parent_cut_percent)
        return

    if not shop_id:
        raise HTTPException(status_code=422, detail="Cashiers require shopId")
    shop = await get_scoped_shop(db, current_user, shop_id)
    if not branch_id:
        raise HTTPException(status_code=422, detail="Cashiers require branchId")
    branch = await db.shopBranches.find_one({"branch_id": branch_id, "shopId": shop["shop_id"]})
    if branch is None:
        raise HTTPException(status_code=422, detail="branchId must belong to shopId")
    validate_assigned_cut(current_user, role, parent_cut_percent)
