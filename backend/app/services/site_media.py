"""Site image processing and shared-filesystem storage. No application secrets."""
import base64
import hashlib
import io
import logging
import os
import re
import tempfile
import warnings
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException
from filelock import FileLock, Timeout
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from core.config import settings

SLOTS = ("auth_hero", "signup_hero", "home_hero", "shop_hero")
MAX_UPLOAD = 2 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 32_000_000
logger = logging.getLogger(__name__)


def media_root():
    return Path(settings.MEDIA_ROOT).resolve()


def media_url_base():
    base = settings.MEDIA_BASE_URL.rstrip("/")
    parsed = urlsplit(base)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise RuntimeError("MEDIA_BASE_URL must be a public URL without credentials, query or fragment")
    if parsed.scheme != "https" and not (not settings.IS_PRODUCTION and local and parsed.scheme == "http"):
        raise RuntimeError("MEDIA_BASE_URL requires HTTPS (localhost HTTP is allowed in development)")
    return base


def require_slot(slot):
    if slot not in SLOTS:
        raise HTTPException(422, "Unknown image slot")
    return slot


def slot_lock(slot):
    require_slot(slot)
    directory = media_root() / ".locks"
    directory.mkdir(parents=True, exist_ok=True)
    # All admin workers use the same MEDIA_ROOT on the VPS. OS locks are released
    # when a worker exits; no expired lease can unlock a still-running writer.
    return FileLock(directory / f"{slot}.lock", thread_local=False)


@contextmanager
def locked_slot(slot):
    lock = slot_lock(slot)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        raise HTTPException(409, "This slot is being updated. Please retry.")
    try:
        yield
    finally:
        lock.release()


def process_image(data):
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Image must be 2 MB or smaller")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise HTTPException(422, "Use a JPEG, PNG or WebP image")
                if getattr(source, "is_animated", False):
                    raise HTTPException(422, "Use a still image, not an animation")
                if max(source.size) > 8000:
                    raise HTTPException(422, "Image dimensions must not exceed 8000 pixels")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                if oriented.width < 800:
                    raise HTTPException(422, "Image must be at least 800 pixels wide")
                rgba = oriented.convert("RGBA")
                profile = source.info.get("icc_profile")
                if profile:
                    # Preserve alpha independently while converting the color channels.
                    colors = oriented if oriented.mode in {"RGB", "CMYK", "LAB", "L"} else oriented.convert("RGB")
                    converted = ImageCms.profileToProfile(colors, ImageCms.ImageCmsProfile(io.BytesIO(profile)), ImageCms.createProfile("sRGB"), outputMode="RGB")
                    converted.putalpha(rgba.getchannel("A"))
                    rgba = converted
                clean = Image.new("RGB", rgba.size, "white")
                clean.paste(rgba, mask=rgba.getchannel("A"))
                # The fresh canvas has no source EXIF, ICC, comments or metadata.
                widths = sorted({w for w in (480, 800, 1200, 1600) if w <= clean.width} | {min(clean.width, 1600)})
                variants = []
                for width in widths:
                    height = max(1, round(clean.height * width / clean.width))
                    output = io.BytesIO()
                    clean.resize((width, height), Image.Resampling.LANCZOS).save(output, "WEBP", quality=78, method=6)
                    variants.append({"width": width, "height": height, "data": output.getvalue()})
                preview = io.BytesIO()
                clean.resize((16, max(1, round(clean.height * 16 / clean.width))), Image.Resampling.LANCZOS).save(preview, "WEBP", quality=40)
                placeholder = "data:image/webp;base64," + base64.b64encode(preview.getvalue()).decode("ascii")
                return hashlib.sha256(data).hexdigest(), variants, placeholder if len(placeholder) <= 4096 else None
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning, ImageCms.PyCMSError):
        raise HTTPException(422, "Image is invalid, damaged, or exceeds the safe pixel limit")


def write_variants(slot, digest, variants):
    directory = media_root() / "site-media" / require_slot(slot)
    directory.mkdir(parents=True, exist_ok=True)
    result, created = [], []
    try:
        for variant in variants:
            filename = f"{digest[:12]}-{variant['width']}.webp"
            target = directory / filename
            if not target.exists():
                descriptor, temporary = tempfile.mkstemp(prefix=".upload-", dir=directory)
                try:
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(variant["data"])
                    os.chmod(temporary, 0o644)  # nginx runs as a separate read-only user
                    os.replace(temporary, target)
                    created.append(target)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            result.append({"url": f"{media_url_base()}/site-media/{slot}/{filename}", "width": variant["width"], "height": variant["height"], "bytes": target.stat().st_size})
        return result, created
    except Exception:
        remove_files(created)
        raise


def remove_files(paths):
    root = media_root() / "site-media"
    for path in paths:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(root):
            raise RuntimeError("Refusing media deletion outside MEDIA_ROOT/site-media")
        try:
            resolved.unlink(missing_ok=True)
        except OSError:
            logger.exception("Could not remove inactive media file: %s", resolved)


def document_files(doc):
    slot, digest = require_slot(doc["slot"]), doc["contentHash"]
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RuntimeError("Invalid media hash")
    return [media_root() / "site-media" / slot / f"{digest[:12]}-{int(v['width'])}.webp" for v in doc["variants"] if 1 <= int(v["width"]) <= 1600]
