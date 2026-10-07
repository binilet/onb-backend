"""Shop Telegram notification settings.

The game server (bingo-server) owns the bot: it consumes the link codes and
test messages written here and fills in ``shops.telegram``. The document
contract is in bingo-server/SHOP_TELEGRAM.md.
"""

import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core.config import settings
from core.db import get_db
from dependencies.auth import get_current_active_user
from models.user import UserInDB
from shop.audit import write_action_log
from shop.authorization import ADMIN, AGENT, SUBAGENT, SYSTEM, require_roles, shop_scope_filter


router = APIRouter(prefix="/api/shop", tags=["shop-telegram"])

TelegramTarget = Literal["general", "deposits", "withdrawals"]
TARGETS: tuple[str, ...] = ("general", "deposits", "withdrawals")
TARGET_LABELS = {"general": "Players' chat", "deposits": "Deposits", "withdrawals": "Withdrawals"}
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_TTL = timedelta(minutes=15)


class TelegramTargetView(BaseModel):
    chatId: str
    threadId: Optional[int] = None
    chatTitle: Optional[str] = None
    chatType: Optional[str] = None
    linkedAt: Optional[datetime] = None
    status: str = "OK"
    lastError: Optional[str] = None
    lastErrorAt: Optional[datetime] = None


class ShopTelegramSettings(BaseModel):
    botUsername: Optional[str] = None
    general: Optional[TelegramTargetView] = None
    deposits: Optional[TelegramTargetView] = None
    withdrawals: Optional[TelegramTargetView] = None


class TelegramLinkCodeView(BaseModel):
    code: str
    command: str
    target: TelegramTarget
    expiresAt: datetime
    botUsername: Optional[str] = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bot_username() -> Optional[str]:
    return settings.SHOP_TELEGRAM_BOT_USERNAME.strip().lstrip("@") or None


async def _managed_shop(db: AsyncIOMotorDatabase, current_user: UserInDB, shop_id: str) -> dict:
    """System, the shop's agents/subagents and the shop's own admin manage its Telegram links."""
    require_roles(current_user, SYSTEM, AGENT, SUBAGENT, ADMIN)
    # $and keeps the caller's scope; merging dicts would let shop_id replace it.
    scope = await shop_scope_filter(db, current_user)
    shop = await db.shops.find_one({"$and": [scope, {"shop_id": shop_id}]})
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return shop


def _settings_view(shop: dict) -> ShopTelegramSettings:
    telegram = shop.get("telegram") or {}
    return ShopTelegramSettings(
        botUsername=_bot_username(),
        **{target: TelegramTargetView(**telegram[target]) for target in TARGETS if telegram.get(target)},
    )


@router.get("/shops/{shop_id}/telegram", response_model=ShopTelegramSettings)
async def get_shop_telegram(
    shop_id: str,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return _settings_view(await _managed_shop(db, current_user, shop_id))


@router.post("/shops/{shop_id}/telegram/{target}/link-code", response_model=TelegramLinkCodeView, status_code=status.HTTP_201_CREATED)
async def create_telegram_link_code(
    shop_id: str,
    target: TelegramTarget,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    await _managed_shop(db, current_user, shop_id)
    # Only the newest code for a destination stays valid.
    await db.telegramLinkCodes.delete_many({"shopId": shop_id, "target": target, "usedAt": None})
    now = _utc_now()
    expires_at = now + CODE_TTL
    for _ in range(5):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        try:
            await db.telegramLinkCodes.insert_one({
                "code": code,
                "shopId": shop_id,
                "target": target,
                "createdByPhone": current_user.phone,
                "expiresAt": expires_at,
                "usedAt": None,
                "createdAt": now,
            })
            break
        except DuplicateKeyError:
            continue
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Could not create a link code; try again")
    display = f"{code[:4]}-{code[4:]}"
    await write_action_log(db, current_user, "CREATE", "SHOP_TELEGRAM_LINK_CODE", shop_id, shop_id=shop_id, detail={"target": target})
    return TelegramLinkCodeView(code=display, command=f"/link {display}", target=target, expiresAt=expires_at, botUsername=_bot_username())


@router.post("/shops/{shop_id}/telegram/{target}/test", status_code=status.HTTP_202_ACCEPTED)
async def send_telegram_test(
    shop_id: str,
    target: TelegramTarget,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    shop = await _managed_shop(db, current_user, shop_id)
    if not (shop.get("telegram") or {}).get(target):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Link this destination first")
    now = _utc_now()
    text = (
        f"🔔 <b>Test message</b>\n🏪 {html.escape(shop.get('shopName', ''))} → {TARGET_LABELS[target]}\n\n"
        "Notifications for this shop will appear here."
    )
    await db.telegramOutbox.insert_one({
        "dedupeKey": f"test:{uuid4()}",
        "shopId": shop_id,
        "target": target,
        "text": text,
        "status": "PENDING",
        "attempts": 0,
        "nextAttemptAt": now,
        "expireAt": now + timedelta(days=30),
        "createdAt": now,
        "updatedAt": now,
    })
    return {"queued": True}


@router.delete("/shops/{shop_id}/telegram/{target}", response_model=ShopTelegramSettings)
async def unlink_telegram_target(
    shop_id: str,
    target: TelegramTarget,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    await _managed_shop(db, current_user, shop_id)
    await db.shops.update_one({"shop_id": shop_id}, {"$unset": {f"telegram.{target}": ""}})
    await write_action_log(db, current_user, "DELETE", "SHOP_TELEGRAM_LINK", shop_id, shop_id=shop_id, detail={"target": target})
    return _settings_view(await _managed_shop(db, current_user, shop_id))
