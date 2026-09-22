from motor.motor_asyncio import AsyncIOMotorDatabase

from models.user import UserInDB
from shop.authorization import get_scoped_branch, get_scoped_shop, require_system


async def require_system_or_shop_agent(
    db: AsyncIOMotorDatabase, current_user: UserInDB, shop_id: str
) -> dict:
    if current_user.role not in {"system", "agent", "subagent"}:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outside shop scope")
    return await get_scoped_shop(db, current_user, shop_id)


async def require_system_or_branch_shop_agent(
    db: AsyncIOMotorDatabase, current_user: UserInDB, branch_id: str
) -> tuple[dict, dict]:
    if current_user.role not in {"system", "agent", "subagent"}:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outside shop scope")
    branch = await get_scoped_branch(db, current_user, branch_id)
    shop = await get_scoped_shop(db, current_user, branch["shopId"])
    return shop, branch
