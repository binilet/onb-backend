from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.db import get_db
from dependencies.auth import get_current_active_user
from models.user import UserInDB
from schemas.userSchema import UserSchema
from shop.access import (
    require_system,
    require_system_or_branch_shop_agent,
    require_system_or_shop_agent,
)
from shop.authorization import (
    ADMIN,
    AGENT,
    CASHIER,
    SUBAGENT,
    SYSTEM,
    branch_scope_filter,
    get_scoped_branch,
    get_scoped_shop,
    get_scoped_staff_user,
    require_roles,
    staff_scope_filter,
    validate_staff_creation,
)
from shop.schemas import (
    Shop,
    ShopBranch,
    ShopBranchCreate,
    ShopBranchUpdate,
    ShopCreate,
    ShopUpdate,
)
from shop.service import (
    create_branch,
    create_shop,
    delete_branch,
    delete_shop,
    get_branch,
    get_shop,
    list_branches,
    list_shops,
    update_branch,
    update_shop,
)
from shop.staff import StaffUserCreate, StaffUserUpdate
from services.user_service import create_user, get_user_by_phone, get_user_by_username
from core.security import get_password_hash
from shop.balances import BalanceTransferRequest, ShopBalance, ShopBalanceLedger
from shop.balance_service import get_scoped_balance, list_scoped_ledgers, transfer_balance
from shop.player_room_wallets import PlayerRoomTopUpRequest, PlayerRoomWallet, PlayerRoomWalletLedger
from shop.player_room_wallet_service import (
    get_own_player_room_wallet,
    get_scoped_player_room_wallet,
    list_scoped_player_room_wallets,
    list_scoped_player_room_wallet_ledgers,
    top_up_player_room_wallet,
)
from shop.games import GameLifecycleRequest, GameParticipant, ShopGame, ShopGameCreate, ShopGameUpdate
from shop.game_service import apply_game_lifecycle_action, create_shop_game, get_scoped_shop_game, list_scoped_game_participants, list_scoped_shop_games, update_shop_game
from shop.audit import ShopActionLog, list_scoped_action_logs, write_action_log


router = APIRouter(prefix="/api/shop", tags=["shop"])


@router.post("/shops", response_model=Shop, status_code=status.HTTP_201_CREATED)
async def create_shop_endpoint(
    payload: ShopCreate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_system(current_user)
    shop = await create_shop(db, payload)
    await write_action_log(db, current_user, "CREATE", "SHOP", shop.shop_id, shop_id=shop.shop_id, detail={"shopName": shop.shopName})
    return shop


@router.get("/shops", response_model=list[Shop])
async def list_shops_endpoint(
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    if current_user.role == SYSTEM:
        return await list_shops(db)
    if current_user.role in {AGENT, SUBAGENT}:
        from shop.authorization import descendant_staff_phones
        phones = [current_user.phone, *(await descendant_staff_phones(db, current_user))]
        return await list_shops(db, representative_phones=phones)
    if not current_user.shopId:
        raise HTTPException(status_code=403, detail="No shop scope assigned")
    return [Shop(**(await get_scoped_shop(db, current_user, current_user.shopId)))]


@router.get("/shops/{shop_id}", response_model=Shop)
async def get_shop_endpoint(
    shop_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    await require_system_or_shop_agent(db, current_user, shop_id)
    shop = await get_shop(db, shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return shop


@router.patch("/shops/{shop_id}", response_model=Shop)
async def update_shop_endpoint(
    shop_id: str,
    payload: ShopUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_system(current_user)
    shop = await update_shop(db, shop_id, payload)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    await write_action_log(db, current_user, "UPDATE", "SHOP", shop_id, shop_id=shop_id, detail=payload.model_dump(exclude_unset=True))
    return shop


@router.delete("/shops/{shop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shop_endpoint(
    shop_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_system(current_user)
    shop = await get_shop(db, shop_id)
    if not await delete_shop(db, shop_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    await write_action_log(db, current_user, "DELETE", "SHOP", shop_id, shop_id=shop_id, detail={"shopName": shop.shopName if shop else None})


@router.post("/shops/{shop_id}/branches", response_model=ShopBranch, status_code=status.HTTP_201_CREATED)
async def create_branch_endpoint(
    shop_id: str,
    payload: ShopBranchCreate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    await require_system_or_shop_agent(db, current_user, shop_id)
    branch = await create_branch(db, shop_id, payload)
    await write_action_log(db, current_user, "CREATE", "BRANCH", branch.branch_id, shop_id=shop_id, branch_id=branch.branch_id, detail={"branchName": branch.branchName, "depositPhone": branch.depositPhone})
    return branch


@router.get("/branches", response_model=list[ShopBranch])
async def list_branches_endpoint(
    shop_id: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    scope = await branch_scope_filter(db, current_user)
    if shop_id is not None:
        await get_scoped_shop(db, current_user, shop_id)
        scope = {**scope, "shopId": shop_id}
    documents = await db.shopBranches.find(scope).to_list(length=None)
    return [ShopBranch(**document) for document in documents]


@router.get("/branches/{branch_id}", response_model=ShopBranch)
async def get_branch_endpoint(
    branch_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    branch = await get_scoped_branch(db, current_user, branch_id)
    return ShopBranch(**branch)


@router.patch("/branches/{branch_id}", response_model=ShopBranch)
async def update_branch_endpoint(
    branch_id: str,
    payload: ShopBranchUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    existing_branch = await get_scoped_branch(db, current_user, branch_id)
    await require_system_or_shop_agent(db, current_user, existing_branch["shopId"])
    branch = await update_branch(db, branch_id, payload)
    if branch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop branch not found")
    await write_action_log(db, current_user, "UPDATE", "BRANCH", branch_id, shop_id=branch.shopId, branch_id=branch_id, detail=payload.model_dump(exclude_unset=True))
    return branch


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch_endpoint(
    branch_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_system(current_user)
    branch = await get_branch(db, branch_id)
    if not await delete_branch(db, branch_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop branch not found")
    await write_action_log(db, current_user, "DELETE", "BRANCH", branch_id, shop_id=branch.shopId if branch else None, branch_id=branch_id)


@router.post("/staff", response_model=UserInDB, status_code=status.HTTP_201_CREATED)
async def create_staff_endpoint(
    payload: StaffUserCreate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    await validate_staff_creation(db, current_user, payload.role, payload.shopId, payload.branchId, payload.parentCutPercent)
    if await get_user_by_phone(db.users, payload.phone):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone already registered")
    if await get_user_by_username(db.users, payload.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")
    user_data = payload.model_dump()
    if user_data.get("parentCutPercent") is None:
        user_data.pop("parentCutPercent", None)
    user_data["parentPhone"] = None if payload.role == AGENT else current_user.phone
    if payload.role == CASHIER:
        user_data["parentCutPercent"] = 100
    user_data["agentId"] = current_user.phone if current_user.role == AGENT else current_user.agentId
    user_data["adminId"] = current_user.phone if current_user.role == ADMIN else None
    staff = await create_user(db.users, UserSchema(**user_data, mustChangePassword=True))
    await write_action_log(db, current_user, "CREATE", "STAFF", staff.phone, shop_id=staff.shopId, branch_id=staff.branchId, detail={"role": staff.role, "username": staff.username})
    return staff


@router.get("/staff", response_model=list[UserInDB])
async def list_staff_endpoint(
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    scope = await staff_scope_filter(db, current_user)
    documents = await db.users.find(scope).to_list(length=None)
    return [UserInDB(**document) for document in documents]


@router.get("/staff/{phone}", response_model=UserInDB)
async def get_staff_endpoint(
    phone: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return UserInDB(**(await get_scoped_staff_user(db, current_user, phone)))


@router.patch("/staff/{phone}", response_model=UserInDB)
async def update_staff_endpoint(
    phone: str,
    payload: StaffUserUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    staff = await get_scoped_staff_user(db, current_user, phone)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return UserInDB(**staff)

    is_self = phone == current_user.phone
    if is_self and set(changes) - {"username"}:
        raise HTTPException(status_code=403, detail="Use the password-change flow for your own password")
    if not is_self and current_user.role == CASHIER:
        raise HTTPException(status_code=403, detail="Cashiers cannot update other staff")
    if staff.get("role") == SYSTEM:
        raise HTTPException(status_code=403, detail="System accounts cannot be changed from the staff directory")

    if "role" in changes and changes["role"] != staff.get("role"):
        allowed_role_changes = {
            SYSTEM: {AGENT, SUBAGENT, ADMIN, CASHIER},
            AGENT: {SUBAGENT, ADMIN},
            SUBAGENT: {ADMIN},
            ADMIN: {CASHIER},
        }
        if changes["role"] not in allowed_role_changes.get(current_user.role, set()):
            raise HTTPException(status_code=403, detail="You cannot assign this staff role")
        direct_report = await db.users.find_one(
            {
                "phone": {"$ne": phone},
                "$or": [
                    {"parentPhone": phone},
                    {"agentId": phone},
                    {"adminId": phone},
                ],
            },
            {"phone": 1},
        )
        if direct_report is not None:
            raise HTTPException(
                status_code=409,
                detail="Move or change this staff member's direct reports before changing their role",
            )
        target_shop_id = changes.get("shopId", staff.get("shopId"))
        target_branch_id = changes.get("branchId", staff.get("branchId"))
        target_cut = changes.get("parentCutPercent", staff.get("parentCutPercent"))
        if changes["role"] in {AGENT, SUBAGENT}:
            target_shop_id = None
            target_branch_id = None
        elif changes["role"] == ADMIN:
            target_branch_id = None
        await validate_staff_creation(
            db,
            current_user,
            changes["role"],
            target_shop_id,
            target_branch_id,
            target_cut,
        )
        changes.update(
            {
                "parentPhone": None if changes["role"] == AGENT else current_user.phone,
                "agentId": (
                    current_user.phone
                    if current_user.role == AGENT
                    else current_user.agentId
                ),
                "adminId": current_user.phone if current_user.role == ADMIN else None,
            }
        )
        if changes["role"] in {AGENT, SUBAGENT}:
            changes.update({"shopId": None, "branchId": None, "adminId": None})
        elif changes["role"] == ADMIN:
            changes["branchId"] = None
            changes["adminId"] = None
        elif changes["role"] == CASHIER:
            changes["parentCutPercent"] = 100

    if "username" in changes and changes["username"] != staff["username"]:
        existing = await get_user_by_username(db.users, changes["username"])
        if existing is not None:
            raise HTTPException(status_code=409, detail="Username already registered")
    effective_role = changes.get("role", staff.get("role"))
    effective_shop_id = changes.get("shopId", staff.get("shopId"))
    if "shopId" in changes and effective_role not in {ADMIN, CASHIER}:
        raise HTTPException(status_code=422, detail="Only admins and cashiers may be assigned to a shop")
    if "branchId" in changes:
        if effective_role != CASHIER:
            raise HTTPException(status_code=422, detail="Only cashier branch assignments may be changed")
        if changes["branchId"] is None:
            raise HTTPException(status_code=422, detail="Cashiers require branchId")
        branch = await db.shopBranches.find_one({"branch_id": changes["branchId"], "shopId": effective_shop_id})
        if branch is None:
            raise HTTPException(status_code=422, detail="branchId must belong to the cashier shop")
    if "parentCutPercent" in changes:
        if changes.get("role", staff.get("role")) == CASHIER:
            changes["parentCutPercent"] = 100
        elif staff.get("parentPhone") != current_user.phone and current_user.role != SYSTEM:
            raise HTTPException(status_code=403, detail="Only the direct parent may change this cut percentage")
        elif effective_role not in {SUBAGENT, ADMIN}:
            raise HTTPException(status_code=422, detail="Cut percentages apply only to subagents and admins")
    if "password" in changes:
        changes["password"] = get_password_hash(changes["password"])
        changes["mustChangePassword"] = True

    await db.users.update_one({"phone": phone}, {"$set": changes})
    updated = await db.users.find_one({"phone": phone})
    await write_action_log(db, current_user, "UPDATE", "STAFF", phone, shop_id=updated.get("shopId"), branch_id=updated.get("branchId"), detail={key: value for key, value in changes.items() if key != "password"})
    return UserInDB(**updated)


@router.post("/balances/transfers", response_model=ShopBalanceLedger, status_code=status.HTTP_201_CREATED)
async def transfer_balance_endpoint(
    payload: BalanceTransferRequest,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN)
    ledger = await transfer_balance(db, current_user, payload)
    await write_action_log(db, current_user, "CREATE", "SHOP_BALANCE_TRANSFER", ledger.ledger_id, shop_id=payload.shopId or current_user.shopId, detail={"toPhone": ledger.toPhone, "amountPoints": str(ledger.amountPoints), "reason": ledger.reason})
    return ledger


@router.get("/balances/{phone}", response_model=ShopBalance)
async def get_balance_endpoint(
    phone: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return await get_scoped_balance(db, current_user, phone)


@router.get("/balance-ledgers", response_model=list[ShopBalanceLedger])
async def list_balance_ledgers_endpoint(
    startAt: Optional[datetime] = None,
    endAt: Optional[datetime] = None,
    phone: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    if startAt and endAt and startAt >= endAt:
        raise HTTPException(status_code=422, detail="endAt must be later than startAt")
    return await list_scoped_ledgers(db, current_user, startAt, endAt, phone)


@router.post("/player-room-wallets/topups", response_model=PlayerRoomWalletLedger, status_code=status.HTTP_201_CREATED)
async def top_up_player_room_wallet_endpoint(
    payload: PlayerRoomTopUpRequest,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    ledger = await top_up_player_room_wallet(db, current_user, payload)
    await write_action_log(db, current_user, "CREATE", "PLAYER_ROOM_TOPUP", ledger.ledger_id, shop_id=payload.shopId, branch_id=payload.branchId, detail={"playerPhone": payload.playerPhone, "amount": str(payload.amount)})
    return ledger


@router.get("/player-room-wallets/me", response_model=PlayerRoomWallet)
async def get_my_player_room_wallet_endpoint(
    shopId: str,
    branchId: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await get_own_player_room_wallet(db, current_user, shopId, branchId)


@router.get("/player-room-wallets", response_model=list[PlayerRoomWallet])
async def list_player_room_wallets_endpoint(
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return await list_scoped_player_room_wallets(db, current_user)


@router.get("/player-room-wallets/{player_phone}", response_model=PlayerRoomWallet)
async def get_player_room_wallet_endpoint(
    player_phone: str,
    shopId: str,
    branchId: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return await get_scoped_player_room_wallet(db, current_user, player_phone, shopId, branchId)


@router.get("/player-room-wallets/{player_phone}/ledgers", response_model=list[PlayerRoomWalletLedger])
async def list_player_room_wallet_ledgers_endpoint(
    player_phone: str,
    shopId: str,
    branchId: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return await list_scoped_player_room_wallet_ledgers(db, current_user, player_phone, shopId, branchId)


@router.post("/games", response_model=ShopGame, status_code=status.HTTP_201_CREATED)
async def create_shop_game_endpoint(
    payload: ShopGameCreate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    game = await create_shop_game(db, current_user, payload)
    await write_action_log(db, current_user, "CREATE", "GAME", game.game_id, shop_id=game.shopId, branch_id=game.branchId, detail={"startMode": game.startMode})
    return game


@router.get("/games", response_model=list[ShopGame])
async def list_shop_games_endpoint(
    startAt: Optional[datetime] = None,
    endAt: Optional[datetime] = None,
    shopId: Optional[str] = None,
    branchId: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    if startAt and endAt and startAt >= endAt:
        raise HTTPException(status_code=422, detail="endAt must be later than startAt")
    filters = {}
    if shopId: filters["shopId"] = shopId
    if branchId: filters["branchId"] = branchId
    if startAt or endAt:
        filters["createdAt"] = {**({"$gte": startAt} if startAt else {}), **({"$lt": endAt} if endAt else {})}
    return await list_scoped_shop_games(db, current_user, filters)


@router.get("/games/{game_id}/participants", response_model=list[GameParticipant])
async def list_game_participants_endpoint(
    game_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return await list_scoped_game_participants(db, current_user, game_id)


@router.patch("/games/{game_id}", response_model=ShopGame)
async def update_shop_game_endpoint(
    game_id: str,
    payload: ShopGameUpdate,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    game = await update_shop_game(db, current_user, game_id, payload)
    await write_action_log(db, current_user, "UPDATE", "GAME", game_id, shop_id=game.shopId, branch_id=game.branchId, detail=payload.model_dump(exclude_unset=True))
    return game


@router.patch("/games/{game_id}/lifecycle", response_model=ShopGame)
async def game_lifecycle_endpoint(game_id: str, payload: GameLifecycleRequest, current_user: UserInDB = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    game = await apply_game_lifecycle_action(db, current_user, game_id, payload)
    await write_action_log(db, current_user, payload.action, "GAME", game_id, shop_id=game.shopId, branch_id=game.branchId)
    return game


@router.get("/action-logs", response_model=list[ShopActionLog])
async def list_action_logs_endpoint(
    logDate: date,
    shopId: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return await list_scoped_action_logs(db, current_user, logDate, shopId)


@router.get("/games/{game_id}", response_model=ShopGame)
async def get_shop_game_endpoint(
    game_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN, CASHIER)
    return await get_scoped_shop_game(db, current_user, game_id)
