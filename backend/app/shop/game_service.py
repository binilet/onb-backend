from datetime import datetime, timedelta, timezone
from bson import ObjectId
from bson.decimal128 import Decimal128
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.user import UserInDB
from shop.authorization import ADMIN, AGENT, CASHIER, SYSTEM
from shop.games import GameLifecycleRequest, GameParticipant, ShopGame, ShopGameCreate, ShopGameUpdate


def _game_from_document(document: dict) -> ShopGame:
    document = document.copy()
    for field in ("betAmount", "totalWinning", "totalCutPercent", "totalCutAmount"):
        if document.get(field) is not None and isinstance(document[field], Decimal128):
            document[field] = document[field].to_decimal()
    return ShopGame(**document)


def _system_note(existing_note: str | None, message: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    entry = f"[System · {timestamp}] {message}"
    return f"{existing_note}\n{entry}" if existing_note else entry


async def game_scope_filter(db: AsyncIOMotorDatabase, current_user: UserInDB) -> dict:
    if current_user.role == SYSTEM:
        return {}
    if current_user.role == AGENT:
        shops = await db.shops.find({"agentId": current_user.phone}, {"shop_id": 1}).to_list(length=None)
        return {"shopId": {"$in": [shop["shop_id"] for shop in shops]}}
    if current_user.role == ADMIN and current_user.shopId:
        return {"shopId": current_user.shopId}
    if current_user.role == CASHIER and current_user.branchId:
        return {"shopId": current_user.shopId, "branchId": current_user.branchId, "createdByPhone": current_user.phone}
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No game scope assigned")


async def _validate_game_location(
    db: AsyncIOMotorDatabase, current_user: UserInDB, shop_id: str, branch_id: str
) -> None:
    shop = await db.shops.find_one({"shop_id": shop_id})
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    branch = await db.shopBranches.find_one({"branch_id": branch_id, "shopId": shop_id})
    if branch is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="branchId must belong to shopId")
    if current_user.role == ADMIN and current_user.shopId != shop_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outside admin shop scope")
    if current_user.role == CASHIER and (current_user.shopId != shop_id or current_user.branchId != branch_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Outside cashier branch scope")


async def _validate_pattern(db: AsyncIOMotorDatabase, payload: ShopGameCreate) -> None:
    if payload.pattern:
        if not ObjectId.is_valid(payload.pattern):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="pattern must be an existing Pattern document ID")
        pattern = await db.patterns.find_one({"_id": ObjectId(payload.pattern), "isActive": True})
        if pattern is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pattern not found or inactive")


async def create_shop_game(
    db: AsyncIOMotorDatabase, current_user: UserInDB, payload: ShopGameCreate
) -> ShopGame:
    if current_user.role not in {SYSTEM, ADMIN, CASHIER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only system, admins, and cashiers may create games")
    await _validate_game_location(db, current_user, payload.shopId, payload.branchId)
    await _validate_pattern(db, payload)
    game = ShopGame(**payload.model_dump(), createdByPhone=current_user.phone)
    document = game.model_dump()
    document["betAmount"] = Decimal128(game.betAmount)
    if game.totalWinning is not None:
        document["totalWinning"] = Decimal128(game.totalWinning)
    document["totalCutPercent"] = Decimal128(game.totalCutPercent)
    await db.games.insert_one(document)
    return game


async def update_shop_game(
    db: AsyncIOMotorDatabase, current_user: UserInDB, game_id: str, payload: ShopGameUpdate
) -> ShopGame:
    if current_user.role not in {SYSTEM, ADMIN, CASHIER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only system, admins, and cashiers may edit games")
    game = await get_scoped_shop_game(db, current_user, game_id)
    changes = payload.model_dump(exclude_unset=True)
    if game.status != "PENDING" and set(changes) - {"note"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending games may have their configuration edited")
    if not changes:
        return game
    if set(changes) == {"note"}:
        changes["updatedAt"] = datetime.now(timezone.utc)
        await db.games.update_one({"game_id": game_id}, {"$set": changes})
        return await get_scoped_shop_game(db, current_user, game_id)

    candidate = game.model_dump()
    candidate.update(changes)
    validation_payload = ShopGameCreate(
        shopId=candidate["shopId"],
        branchId=candidate["branchId"],
        pattern=candidate["pattern"],
        dynamicPattern=candidate["dynamicPattern"],
        betAmount=candidate["betAmount"],
        totalWinning=candidate["totalWinning"],
        totalCutPercent=candidate["totalCutPercent"],
        startMode=candidate["startMode"],
        scheduledStartAt=candidate["scheduledStartAt"],
        note=candidate["note"],
    )
    await _validate_pattern(db, validation_payload)

    for field in ("betAmount", "totalWinning", "totalCutPercent"):
        if field in changes and changes[field] is not None:
            changes[field] = Decimal128(changes[field])
    changes["updatedAt"] = datetime.now(timezone.utc)
    await db.games.update_one({"game_id": game_id}, {"$set": changes})
    return await get_scoped_shop_game(db, current_user, game_id)


async def list_scoped_shop_games(db: AsyncIOMotorDatabase, current_user: UserInDB, filters: dict | None = None) -> list[ShopGame]:
    scope = await game_scope_filter(db, current_user)
    query = scope if not filters else {"$and": [scope, filters]} if scope else filters
    documents = await db.games.find(query).sort("createdAt", -1).to_list(length=None)
    return [_game_from_document(document) for document in documents]


async def get_scoped_shop_game(
    db: AsyncIOMotorDatabase, current_user: UserInDB, game_id: str
) -> ShopGame:
    scope = await game_scope_filter(db, current_user)
    document = await db.games.find_one({**scope, "game_id": game_id})
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return _game_from_document(document)


async def list_scoped_game_participants(db: AsyncIOMotorDatabase, current_user: UserInDB, game_id: str) -> list[GameParticipant]:
    await get_scoped_shop_game(db, current_user, game_id)
    documents = await db.gameParticipants.find({"gameId": game_id}).to_list(length=None)
    for document in documents:
        if document.get("winAmount") is not None and isinstance(document["winAmount"], Decimal128):
            document["winAmount"] = document["winAmount"].to_decimal()
    return [GameParticipant(**document) for document in documents]


async def apply_game_lifecycle_action(db: AsyncIOMotorDatabase, current_user: UserInDB, game_id: str, request: GameLifecycleRequest) -> ShopGame:
    if current_user.role not in {SYSTEM, ADMIN, CASHIER}:
        raise HTTPException(status_code=403, detail="Only system, admins, and cashiers may control games")
    game = await get_scoped_shop_game(db, current_user, game_id)
    if request.action == "START":
        if game.status != "PENDING":
            raise HTTPException(status_code=409, detail="Only pending games can be started")
        if game.isFrozen:
            raise HTTPException(status_code=409, detail="Unfreeze the game before starting it")
        if game.totalWinning is None or game.totalWinning <= 0:
            raise HTTPException(status_code=422, detail="Set a positive totalWinning before starting the game")
        starts_at = datetime.now(timezone.utc) + timedelta(seconds=20)
        changes = {"scheduledStartAt": starts_at, "isPurchaseLocked": True, "note": _system_note(game.note, f"Game start locked by {current_user.phone}; countdown ends at {starts_at.isoformat()}"), "updatedAt": datetime.now(timezone.utc)}
    elif request.action == "VOID":
        if game.status == "COMPLETE":
            raise HTTPException(status_code=409, detail="Completed games cannot be voided")
        changes = {"status": "VOID", "isFrozen": False, "note": _system_note(game.note, f"Game voided by {current_user.phone}"), "updatedAt": datetime.now(timezone.utc)}
    elif request.action == "FREEZE":
        if game.status in {"COMPLETE", "VOID"}:
            raise HTTPException(status_code=409, detail="Completed or void games cannot be frozen")
        changes = {"isFrozen": True, "frozenByPhone": current_user.phone, "frozenByRole": current_user.role, "note": _system_note(game.note, f"Game frozen by {current_user.phone}"), "updatedAt": datetime.now(timezone.utc)}
    else:
        if not game.isFrozen:
            return game
        if current_user.role == CASHIER and game.frozenByRole in {ADMIN, SYSTEM}:
            raise HTTPException(status_code=403, detail="Cashiers cannot unfreeze an admin or system freeze")
        changes = {"isFrozen": False, "frozenByPhone": None, "frozenByRole": None, "note": _system_note(game.note, f"Game unfrozen by {current_user.phone}"), "updatedAt": datetime.now(timezone.utc)}
    await db.games.update_one({"game_id": game_id}, {"$set": changes})
    return await get_scoped_shop_game(db, current_user, game_id)
