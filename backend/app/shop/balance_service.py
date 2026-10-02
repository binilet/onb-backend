from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from bson.decimal128 import Decimal128
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from models.user import UserInDB
from shop.authorization import ADMIN, AGENT, CASHIER, SUBAGENT, SYSTEM, get_scoped_staff_user
from shop.balances import BalanceTransferRequest, ShopBalance, ShopBalanceLedger


def convert_to_points(source_amount: Decimal, recipient_cut_percent: Decimal) -> Decimal:
    """Convert a sender amount using the recipient's assigned staff cut."""
    if recipient_cut_percent <= 0:
        raise ValueError("Recipient cut percentage must be greater than zero")
    return source_amount * (Decimal("100") / recipient_cut_percent)


def _decimal(value: Decimal | Decimal128 | int | float | str) -> Decimal:
    return value.to_decimal() if isinstance(value, Decimal128) else Decimal(str(value))


def _balance_from_document(document: dict) -> ShopBalance:
    document = document.copy()
    document["currentBalance"] = _decimal(document.get("currentBalance", Decimal("0")))
    return ShopBalance(**document)


def _ledger_from_document(document: dict) -> ShopBalanceLedger:
    document = document.copy()
    document["amountPoints"] = _decimal(document["amountPoints"])
    if document.get("etbAmount") is not None:
        document["etbAmount"] = _decimal(document["etbAmount"])
    # Read historical ledger records written before the staff-cut migration.
    if document.get("cutPercentApplied") is None and document.get("systemCutPercentApplied") is not None:
        document["cutPercentApplied"] = document["systemCutPercentApplied"]
    if document.get("cutPercentApplied") is not None:
        document["cutPercentApplied"] = _decimal(document["cutPercentApplied"])
    if document.get("sourceAmountPoints") is not None:
        document["sourceAmountPoints"] = _decimal(document["sourceAmountPoints"])
    return ShopBalanceLedger(**document)


async def ensure_balance_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.shopBalances.create_index("phone", unique=True, name="shop_balance_phone_unique")
    await db.shopBalanceLedgers.create_index("ledger_id", unique=True, name="shop_balance_ledger_id_unique")
    await db.shopBalanceLedgers.create_index("idempotencyKey", unique=True, name="shop_balance_ledger_idempotency_unique")
    await db.shopBalanceLedgers.create_index([("createdAt", -1), ("fromPhone", 1), ("toPhone", 1)], name="shop_balance_ledger_scope_date")
    await db.users.create_index([("parentPhone", 1), ("role", 1)], name="shop_staff_parent_role")


async def _transfer_details(
    db: AsyncIOMotorDatabase, current_user: UserInDB, request: BalanceTransferRequest
) -> tuple[Optional[str], Decimal, Optional[Decimal], Optional[Decimal], Optional[Decimal], str]:
    recipient = await db.users.find_one({"phone": request.toPhone})
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    if current_user.role == SYSTEM:
        recipient_role = recipient.get("role")
        if recipient_role not in {AGENT, SUBAGENT, ADMIN, CASHIER}:
            raise HTTPException(status_code=403, detail="System transfers must target a Shop staff account")
        if request.etbAmount is None or request.amountPoints is not None:
            raise HTTPException(status_code=422, detail="System grants require an ETB amount only")
        cut_percent = _decimal(recipient.get("parentCutPercent") or 0)
        try:
            points = convert_to_points(request.etbAmount, cut_percent)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        reason_by_role = {
            AGENT: "SYSTEM_TO_AGENT_GRANT",
            SUBAGENT: "SYSTEM_TO_SUBAGENT_GRANT",
            ADMIN: "SYSTEM_TO_ADMIN_GRANT",
            CASHIER: "SYSTEM_TO_CASHIER_GRANT",
        }
        return None, points, None, request.etbAmount, cut_percent, reason_by_role[recipient_role]

    if current_user.role in {AGENT, SUBAGENT}:
        allowed_roles = {SUBAGENT, ADMIN, CASHIER} if current_user.role == AGENT else {ADMIN, CASHIER}
        direct_parent = recipient.get("parentPhone") or recipient.get("agentId")
        if recipient.get("role") not in allowed_roles or direct_parent != current_user.phone:
            raise HTTPException(status_code=403, detail="Recipient is outside the direct staff hierarchy")
        if request.amountPoints is None or request.etbAmount is not None:
            raise HTTPException(status_code=422, detail="Hierarchy transfers require amountPoints only")
        cut_percent = _decimal(
            recipient.get("parentCutPercent")
            or recipient.get("adminPercent")
            or recipient.get("agentPercent")
            or 0
        )
        try:
            credited_points = convert_to_points(request.amountPoints, cut_percent)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Recipient parent cut percentage is not configured") from exc
        reason = (
            "AGENT_TO_SUBAGENT_TRANSFER" if recipient.get("role") == SUBAGENT else
            "AGENT_TO_ADMIN_TRANSFER" if recipient.get("role") == ADMIN and current_user.role == AGENT else
            "SUBAGENT_TO_ADMIN_TRANSFER" if recipient.get("role") == ADMIN else
            "AGENT_TO_CASHIER_TRANSFER" if current_user.role == AGENT else
            "SUBAGENT_TO_CASHIER_TRANSFER"
        )
        return current_user.phone, credited_points, request.amountPoints, None, cut_percent, reason

    if current_user.role == ADMIN:
        # ``parentPhone`` is the current hierarchy field, while older cashier
        # records can still carry their owning admin in ``adminId``.  Treat
        # either explicit direct-admin link as valid; preferring one field with
        # ``or`` made valid legacy cashiers fail when the other field was stale.
        is_direct_cashier = (
            recipient.get("role") == CASHIER
            and (
                recipient.get("parentPhone") == current_user.phone
                or recipient.get("adminId") == current_user.phone
            )
        )
        if not is_direct_cashier:
            raise HTTPException(status_code=403, detail="Admins may transfer to their direct cashiers only")
        if request.amountPoints is None or request.etbAmount is not None:
            raise HTTPException(status_code=422, detail="Admin transfers require amountPoints only")
        return current_user.phone, request.amountPoints, request.amountPoints, None, Decimal("100"), "ADMIN_TO_CASHIER_TRANSFER"

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cashiers cannot transfer balances")


async def transfer_balance(
    db: AsyncIOMotorDatabase, current_user: UserInDB, request: BalanceTransferRequest
) -> ShopBalanceLedger:
    await ensure_balance_indexes(db)
    from_phone, amount_points, source_amount_points, etb_amount, applied_percent, reason = await _transfer_details(db, current_user, request)

    existing = await db.shopBalanceLedgers.find_one({"idempotencyKey": request.idempotencyKey})
    if existing is not None:
        existing_ledger = _ledger_from_document(existing)
        if (
            existing_ledger.fromPhone != from_phone
            or existing_ledger.toPhone != request.toPhone
            or existing_ledger.amountPoints != amount_points
            or existing_ledger.sourceAmountPoints != source_amount_points
            or existing_ledger.reason != reason
            or existing_ledger.etbAmount != etb_amount
            or existing_ledger.cutPercentApplied != applied_percent
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotencyKey was already used for a different transfer")
        return existing_ledger

    ledger = ShopBalanceLedger(
        fromPhone=from_phone,
        toPhone=request.toPhone,
        amountPoints=amount_points,
        sourceAmountPoints=source_amount_points,
        etbAmount=etb_amount,
        cutPercentApplied=applied_percent,
        reason=reason,
        idempotencyKey=request.idempotencyKey,
    )
    now = datetime.now(timezone.utc)
    try:
        async with await db.client.start_session() as session:
            async with session.start_transaction():
                existing = await db.shopBalanceLedgers.find_one({"idempotencyKey": request.idempotencyKey}, session=session)
                if existing is not None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotencyKey is already in use")

                amount_db = Decimal128(amount_points)
                if from_phone is not None:
                    debit_amount = source_amount_points or amount_points
                    sender_update = await db.shopBalances.update_one(
                        {"phone": from_phone, "currentBalance": {"$gte": Decimal128(debit_amount)}},
                        {"$inc": {"currentBalance": Decimal128(-debit_amount)}, "$set": {"updatedAt": now}},
                        session=session,
                    )
                    if sender_update.matched_count != 1:
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient sender balance")

                await db.shopBalances.update_one(
                    {"phone": request.toPhone},
                    {"$setOnInsert": {"phone": request.toPhone}, "$inc": {"currentBalance": amount_db}, "$set": {"updatedAt": now}},
                    upsert=True,
                    session=session,
                )
                ledger_document = ledger.model_dump()
                ledger_document["amountPoints"] = amount_db
                if source_amount_points is not None:
                    ledger_document["sourceAmountPoints"] = Decimal128(source_amount_points)
                if etb_amount is not None:
                    ledger_document["etbAmount"] = Decimal128(etb_amount)
                if applied_percent is not None:
                    ledger_document["cutPercentApplied"] = Decimal128(applied_percent)
                await db.shopBalanceLedgers.insert_one(ledger_document, session=session)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="idempotencyKey is already in use") from exc
    return ledger


async def get_scoped_balance(
    db: AsyncIOMotorDatabase, current_user: UserInDB, phone: str
) -> ShopBalance:
    if current_user.role != SYSTEM and phone != current_user.phone:
        await get_scoped_staff_user(db, current_user, phone)
    document = await db.shopBalances.find_one({"phone": phone})
    return _balance_from_document(document) if document else ShopBalance(phone=phone)


async def list_scoped_ledgers(
    db: AsyncIOMotorDatabase,
    current_user: UserInDB,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    phone: str | None = None,
) -> list[ShopBalanceLedger]:
    if current_user.role == SYSTEM:
        query = {}
    else:
        from shop.authorization import staff_scope_filter

        staff_scope = await staff_scope_filter(db, current_user)
        staff_documents = await db.users.find(staff_scope, {"phone": 1}).to_list(length=None)
        phones = [current_user.phone, *[document["phone"] for document in staff_documents]]
        query = {"$or": [{"fromPhone": {"$in": phones}}, {"toPhone": {"$in": phones}}]}
    filters = [query] if query else []
    if start_at is not None or end_at is not None:
        created_at_filter: dict[str, datetime] = {}
        if start_at is not None:
            created_at_filter["$gte"] = start_at
        if end_at is not None:
            created_at_filter["$lt"] = end_at
        filters.append({"createdAt": created_at_filter})
    if phone:
        filters.append({"$or": [{"fromPhone": phone}, {"toPhone": phone}]})

    filtered_query = {} if not filters else filters[0] if len(filters) == 1 else {"$and": filters}
    documents = await db.shopBalanceLedgers.find(filtered_query).sort("createdAt", -1).limit(500).to_list(length=500)
    return [_ledger_from_document(document) for document in documents]
