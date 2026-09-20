from datetime import datetime, timezone
from decimal import Decimal

from bson.decimal128 import Decimal128
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from models.user import UserInDB
from shop.authorization import ADMIN, AGENT, CASHIER, SYSTEM
from shop.player_room_wallets import PlayerRoomTopUpRequest, PlayerRoomWallet, PlayerRoomWalletLedger


def _decimal(value: Decimal | Decimal128 | int | float | str) -> Decimal:
    return value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))


def _wallet_from_document(document: dict) -> PlayerRoomWallet:
    document = document.copy()
    document["currentBalance"] = _decimal(document.get("currentBalance", Decimal("0")))
    return PlayerRoomWallet(**document)


def _wallet_ledger_from_document(document: dict) -> PlayerRoomWalletLedger:
    document = document.copy()
    document["amount"] = _decimal(document["amount"])
    return PlayerRoomWalletLedger(**document)


async def ensure_player_room_wallet_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.playerRoomWallets.create_index(
        [("playerPhone", 1), ("shopId", 1)], unique=True, name="player_room_wallet_player_shop_unique"
    )
    await db.playerRoomWalletLedgers.create_index("ledger_id", unique=True, name="player_room_wallet_ledger_id_unique")
    await db.playerRoomWalletLedgers.create_index(
        "idempotencyKey", unique=True, name="player_room_wallet_ledger_idempotency_unique"
    )


async def _validate_room_scope(
    db: AsyncIOMotorDatabase, current_user: UserInDB, shop_id: str, branch_id: str | None
) -> None:
    shop = await db.shops.find_one({"shop_id": shop_id})
    if shop is None:
        raise HTTPException(status_code=404, detail="Shop not found")
    if current_user.role == AGENT and shop.get("agentId") != current_user.phone:
        raise HTTPException(status_code=403, detail="Outside agent shop scope")
    if current_user.role in {ADMIN, CASHIER} and current_user.shopId != shop_id:
        raise HTTPException(status_code=403, detail="Outside staff shop scope")
    if branch_id is not None:
        branch = await db.shopBranches.find_one({"branch_id": branch_id, "shopId": shop_id})
        if branch is None:
            raise HTTPException(status_code=422, detail="branchId must belong to shopId")


async def top_up_player_room_wallet(
    db: AsyncIOMotorDatabase, current_user: UserInDB, request: PlayerRoomTopUpRequest
) -> PlayerRoomWalletLedger:
    if current_user.role not in {ADMIN, CASHIER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins and cashiers may top up player wallets")
    await _validate_room_scope(db, current_user, request.shopId, request.branchId)
    player = await db.users.find_one({"phone": request.playerPhone})
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    if player.get("role") not in {None, "user"}:
        raise HTTPException(status_code=422, detail="Top-up recipient must be a player account")

    await ensure_player_room_wallet_indexes(db)
    existing = await db.playerRoomWalletLedgers.find_one({"idempotencyKey": request.idempotencyKey})
    if existing is not None:
        ledger = _wallet_ledger_from_document(existing)
        if (
            ledger.playerPhone != request.playerPhone
            or ledger.shopId != request.shopId
            or ledger.branchId != request.branchId
            or ledger.amount != request.amount
            or ledger.reason != "CASHIER_TOPUP"
            or ledger.toppedUpByPhone != current_user.phone
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotencyKey was already used for a different top-up")
        return ledger

    ledger = PlayerRoomWalletLedger(
        playerPhone=request.playerPhone,
        shopId=request.shopId,
        branchId=request.branchId,
        amount=request.amount,
        reason="CASHIER_TOPUP",
        toppedUpByPhone=current_user.phone,
        idempotencyKey=request.idempotencyKey,
    )
    now = datetime.now(timezone.utc)
    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                existing = await db.playerRoomWalletLedgers.find_one({"idempotencyKey": request.idempotencyKey}, session=session)
                if existing is not None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotencyKey is already in use")
                await db.playerRoomWallets.update_one(
                    {"playerPhone": request.playerPhone, "shopId": request.shopId},
                    {
                        "$setOnInsert": {
                            "playerPhone": request.playerPhone,
                            "shopId": request.shopId,
                            "branchId": request.branchId,
                            "isWithdrawable": True,
                        },
                        "$inc": {"currentBalance": Decimal128(request.amount)},
                        "$set": {"updatedAt": now},
                    },
                    upsert=True,
                    session=session,
                )
                ledger_document = ledger.model_dump()
                ledger_document["amount"] = Decimal128(request.amount)
                await db.playerRoomWalletLedgers.insert_one(ledger_document, session=session)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotencyKey is already in use") from exc
    return ledger


async def get_own_player_room_wallet(
    db: AsyncIOMotorDatabase, current_user: UserInDB, shop_id: str, branch_id: str | None
) -> PlayerRoomWallet:
    await _validate_room_scope(db, current_user, shop_id, branch_id)
    is_withdrawable = current_user.role in {None, "user"}
    await db.playerRoomWallets.update_one(
        {"playerPhone": current_user.phone, "shopId": shop_id},
        {
            "$setOnInsert": {
                "playerPhone": current_user.phone,
                "shopId": shop_id,
                "branchId": branch_id,
                "currentBalance": Decimal128(Decimal("0")),
                "isWithdrawable": is_withdrawable,
                "updatedAt": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    document = await db.playerRoomWallets.find_one({"playerPhone": current_user.phone, "shopId": shop_id})
    return _wallet_from_document(document)


async def get_scoped_player_room_wallet(
    db: AsyncIOMotorDatabase,
    current_user: UserInDB,
    player_phone: str,
    shop_id: str,
    branch_id: str | None,
) -> PlayerRoomWallet:
    """Read one player wallet without creating a new wallet record."""
    await _validate_room_scope(db, current_user, shop_id, branch_id)
    player = await db.users.find_one({"phone": player_phone})
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    document = await db.playerRoomWallets.find_one({"playerPhone": player_phone, "shopId": shop_id})
    if document is not None:
        return _wallet_from_document(document)
    return PlayerRoomWallet(
        playerPhone=player_phone,
        shopId=shop_id,
        branchId=branch_id,
        currentBalance=Decimal("0"),
        isWithdrawable=player.get("role") in {None, "user"},
    )


async def list_scoped_player_room_wallet_ledgers(
    db: AsyncIOMotorDatabase,
    current_user: UserInDB,
    player_phone: str,
    shop_id: str,
    branch_id: str | None,
) -> list[PlayerRoomWalletLedger]:
    await _validate_room_scope(db, current_user, shop_id, branch_id)
    documents = await db.playerRoomWalletLedgers.find(
        {"playerPhone": player_phone, "shopId": shop_id}
    ).sort("createdAt", -1).to_list(length=None)
    return [_wallet_ledger_from_document(document) for document in documents]


async def list_scoped_player_room_wallets(
    db: AsyncIOMotorDatabase, current_user: UserInDB
) -> list[PlayerRoomWallet]:
    if current_user.role == SYSTEM:
        scope = {}
    elif current_user.role == AGENT:
        shops = await db.shops.find({"agentId": current_user.phone}, {"shop_id": 1}).to_list(length=None)
        scope = {"shopId": {"$in": [shop["shop_id"] for shop in shops]}}
    elif current_user.role in {ADMIN, CASHIER} and current_user.shopId:
        scope = {"shopId": current_user.shopId}
    else:
        raise HTTPException(status_code=403, detail="No player wallet scope assigned")

    documents = await db.playerRoomWallets.find(scope).sort("updatedAt", -1).to_list(length=None)
    return [_wallet_from_document(document) for document in documents]
