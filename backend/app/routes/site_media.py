import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from core.db import get_db
from dependencies.auth import get_current_active_user
from services.site_media import MAX_UPLOAD, SLOTS, document_files, locked_slot, media_root, process_image, remove_files, require_slot, write_variants

router = APIRouter(prefix="/admin/site-media", tags=["Site media"])
processing_slots = asyncio.Semaphore(2)
logger = logging.getLogger(__name__)
Slot = Literal["auth_hero", "signup_hero", "home_hero", "shop_hero"]


async def system_user(user=Depends(get_current_active_user)):
    if user.role != "system":
        raise HTTPException(403, "Only System can manage site images")
    return user


async def ensure_indexes(db):
    await db.siteMedia.create_index("slot", name="site_media_active_slot", unique=True, partialFilterExpression={"isActive": True})
    await db.siteMedia.create_index([("slot", 1), ("contentHash", 1)], name="site_media_content", unique=True)


def serialize(doc):
    # storageDir/hash remain server-side even for the management UI.
    fields = ("slot", "isActive", "url", "variants", "width", "height", "alt", "focalX", "focalY", "placeholder", "originalName", "uploadedBy", "createdAt", "updatedAt")
    return {"id": str(doc["_id"]), **{k: doc.get(k) for k in fields}}


def object_id(value):
    if not ObjectId.is_valid(value):
        raise HTTPException(404, "Image not found")
    return ObjectId(value)


class AltText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str = Field(default="", max_length=500)
    am: str = Field(default="", max_length=500)
    om: str = Field(default="", max_length=500)


class MediaPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alt: AltText | None = None
    focalX: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    focalY: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    isActive: bool | None = None


@router.get("")
async def list_media(slot: Slot | None = None, user=Depends(system_user), db=Depends(get_db)):
    query = {"slot": slot} if slot else {"slot": {"$in": list(SLOTS)}}
    return [serialize(doc) async for doc in db.siteMedia.find(query).sort("createdAt", -1)]


@router.post("")
async def upload_media(
    slot: Slot = Form(...), file: UploadFile = File(...),
    alt_en: str = Form("", max_length=500), alt_am: str = Form("", max_length=500), alt_om: str = Form("", max_length=500),
    focalX: float = Form(50, ge=0, le=100, allow_inf_nan=False), focalY: float = Form(50, ge=0, le=100, allow_inf_nan=False),
    activate: bool = Form(False), user=Depends(system_user), db=Depends(get_db),
):
    try:
        data = await file.read(MAX_UPLOAD + 1)
    finally:
        await file.close()
    async with processing_slots:
        digest, variants, placeholder = await run_in_threadpool(process_image, data)
    now = datetime.now(timezone.utc)
    with locked_slot(slot):
        collision = await db.siteMedia.find_one({"slot": slot, "contentHash": {"$regex": "^" + digest[:12], "$ne": digest}})
        if collision:
            raise HTTPException(409, "Image hash prefix collision; use a different image")
        existing = await db.siteMedia.find_one({"slot": slot, "contentHash": digest})
        stored, created_files = await run_in_threadpool(write_variants, slot, digest, variants)
        largest = stored[-1]
        doc = {
            "_id": existing["_id"] if existing else ObjectId(), "slot": slot,
            "isActive": bool(activate or (existing and existing.get("isActive"))),
            "url": largest["url"], "variants": stored, "width": largest["width"], "height": largest["height"],
            "alt": {"en": alt_en, "am": alt_am, "om": alt_om}, "focalX": focalX, "focalY": focalY,
            "placeholder": placeholder, "contentHash": digest, "storageDir": str(media_root() / "site-media" / slot),
            "originalName": Path((file.filename or "image").replace("\\", "/")).name[:200],
            "uploadedBy": existing.get("uploadedBy") if existing else user.phone,
            "createdAt": existing["createdAt"] if existing else now, "updatedAt": now,
        }
        async def persist(session):
            if doc["isActive"]:
                await db.siteMedia.update_many({"slot": slot, "isActive": True, "_id": {"$ne": doc["_id"]}}, {"$set": {"isActive": False, "updatedAt": now}}, session=session)
            await db.siteMedia.replace_one({"_id": doc["_id"]}, doc, upsert=True, session=session)
        try:
            async with await db.client.start_session() as session:
                await session.with_transaction(persist)
        except Exception:
            # Unknown commit results must not delete files that were committed.
            # If Mongo is unavailable, leave files for later reconciliation.
            try:
                if not await db.siteMedia.find_one({"slot": slot, "contentHash": digest}):
                    await run_in_threadpool(remove_files, created_files)
            except Exception:
                logger.exception("Media cleanup deferred after database failure")
            raise
    return serialize(doc)


@router.post("/slots/{slot}/reset")
async def reset_slot(slot: Slot, user=Depends(system_user), db=Depends(get_db)):
    with locked_slot(slot):
        await db.siteMedia.update_many({"slot": slot, "isActive": True}, {"$set": {"isActive": False, "updatedAt": datetime.now(timezone.utc)}})
    return {"slot": slot, "reset": True}


@router.patch("/{media_id}")
async def patch_media(media_id: str, payload: MediaPatch, user=Depends(system_user), db=Depends(get_db)):
    oid = object_id(media_id)
    doc = await db.siteMedia.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Image not found")
    changes = payload.model_dump(exclude_none=True)
    changes["updatedAt"] = datetime.now(timezone.utc)
    with locked_slot(doc["slot"]):
        async def persist(session):
            current = await db.siteMedia.find_one({"_id": oid}, session=session)
            if not current:
                raise HTTPException(404, "Image not found")
            if changes.get("isActive"):
                if not all(path.is_file() for path in document_files(current)):
                    raise HTTPException(409, "Image files are missing. Upload this image again.")
                await db.siteMedia.update_many({"slot": current["slot"], "isActive": True, "_id": {"$ne": oid}}, {"$set": {"isActive": False, "updatedAt": changes["updatedAt"]}}, session=session)
            await db.siteMedia.update_one({"_id": oid}, {"$set": changes}, session=session)
        try:
            async with await db.client.start_session() as session:
                await session.with_transaction(persist)
        except DuplicateKeyError:
            raise HTTPException(409, "This slot changed. Refresh and retry.")
        return serialize(await db.siteMedia.find_one({"_id": oid}))


@router.delete("/{media_id}")
async def delete_media(media_id: str, user=Depends(system_user), db=Depends(get_db)):
    oid = object_id(media_id)
    doc = await db.siteMedia.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Image not found")
    with locked_slot(doc["slot"]):
        deleted = await db.siteMedia.find_one_and_delete({"_id": oid, "isActive": False})
        if not deleted:
            raise HTTPException(409, "Deactivate this image before deleting it")
        await run_in_threadpool(remove_files, document_files(deleted))
    return {"deleted": True}


class MediaUploadLimit:
    """Bound multipart requests before Starlette spools files (including chunked)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path", "").rstrip("/") not in {"/admin/site-media", "/api/admin/site-media"}:
            return await self.app(scope, receive, send)
        limit = MAX_UPLOAD + 65536  # multipart envelope; actual file remains 2 MB
        headers = dict(scope.get("headers", []))
        try:
            too_big = int(headers.get(b"content-length", b"0")) > limit
        except ValueError:
            return await JSONResponse({"detail": "Invalid Content-Length"}, 400)(scope, receive, send)
        if too_big:
            return await JSONResponse({"detail": "Image must be 2 MB or smaller"}, 413)(scope, receive, send)
        consumed = 0
        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > limit:
                raise HTTPException(413, "Image must be 2 MB or smaller")
            return message
        return await self.app(scope, bounded_receive, send)
