"""Run: python -m unittest tests.test_site_media -v (from backend/app).

Uses only a generated test DB on localhost, never the configured application DB.
Requires a local replica set and httpx. Tests don't start the game's background jobs.
"""
import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image

from core.config import settings
from core.db import get_db
from dependencies.auth import get_current_active_user
from routes.site_media import MediaUploadLimit, ensure_indexes, router
from services.site_media import MAX_UPLOAD, process_image


def picture(color="red", size=(1000, 600), fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, fmt)
    return output.getvalue()


class ImageProcessingTests(unittest.TestCase):
    def test_sizes_placeholder_and_metadata(self):
        _, variants, placeholder = process_image(picture())
        self.assertEqual([v["width"] for v in variants], [480, 800, 1000])
        self.assertLessEqual(len(placeholder), 4096)
        for variant in variants:
            with Image.open(io.BytesIO(variant["data"])) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertFalse(image.getexif())
                self.assertNotIn("icc_profile", image.info)

    def test_invalid_and_over_limit(self):
        cases = [b"<svg/>", picture(fmt="GIF"), picture(size=(300, 300)), b"x" * (MAX_UPLOAD + 1), picture(size=(8001, 1))]
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(HTTPException):
                process_image(data)

    def test_transparency_is_white(self):
        output = io.BytesIO()
        Image.new("RGBA", (800, 400), (0, 0, 0, 0)).save(output, "PNG")
        _, variants, _ = process_image(output.getvalue())
        with Image.open(io.BytesIO(variants[-1]["data"])) as image:
            self.assertTrue(all(c > 245 for c in image.getpixel((0, 0))[:3]))

    def test_orientation_before_width_validation(self):
        output = io.BytesIO()
        image = Image.new("RGB", (600, 1000), "blue")
        exif = image.getexif()
        exif[274] = 6
        image.save(output, "JPEG", exif=exif)
        _, variants, _ = process_image(output.getvalue())
        self.assertEqual((variants[-1]["width"], variants[-1]["height"]), (1000, 600))


class MediaApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mongo = AsyncIOMotorClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
        self.db_name = "site_media_test_" + uuid4().hex
        self.db = self.mongo[self.db_name]
        await ensure_indexes(self.db)
        self.directory = tempfile.TemporaryDirectory(prefix="hagere-media-test-")
        self.old_settings = (settings.MEDIA_ROOT, settings.MEDIA_BASE_URL, settings.IS_PRODUCTION)
        settings.MEDIA_ROOT = self.directory.name
        settings.MEDIA_BASE_URL = "http://localhost:8000/media"
        settings.IS_PRODUCTION = False
        self.role = "system"
        app = FastAPI()
        app.include_router(router)
        app.add_middleware(MediaUploadLimit)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(role=self.role, phone="test-system")
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.http.aclose()
        self.assertTrue(self.db_name.startswith("site_media_test_"))
        await self.mongo.drop_database(self.db_name)
        self.mongo.close()
        settings.MEDIA_ROOT, settings.MEDIA_BASE_URL, settings.IS_PRODUCTION = self.old_settings
        self.directory.cleanup()

    async def upload(self, color="red", activate=True, data=None):
        return await self.http.post("/admin/site-media", data={"slot": "home_hero", "activate": str(activate).lower()}, files={"file": ("banner.png", data if data is not None else picture(color), "image/png")})

    async def test_lifecycle_dedupe_and_files(self):
        first = await self.upload()
        self.assertEqual(first.status_code, 200, first.text)
        first = first.json()
        duplicate = await self.upload()
        self.assertEqual(first["id"], duplicate.json()["id"])
        self.assertEqual(await self.db.siteMedia.count_documents({}), 1)
        second = await self.upload("blue")
        self.assertEqual(second.status_code, 200, second.text)
        second = second.json()
        self.assertEqual(await self.db.siteMedia.count_documents({"isActive": True}), 1)
        self.assertEqual((await self.http.delete('/admin/site-media/' + second['id'])).status_code, 409)
        restored = await self.http.patch('/admin/site-media/' + first['id'], json={"isActive": True, "alt": {"en": "Restored"}, "focalY": 25})
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["alt"]["en"], "Restored")
        self.assertEqual((await self.http.delete('/admin/site-media/' + second['id'])).status_code, 200)
        self.assertEqual(len(list(Path(self.directory.name).rglob("*.webp"))), 3)
        self.assertEqual((await self.http.post('/admin/site-media/slots/home_hero/reset')).status_code, 200)
        self.assertEqual(await self.db.siteMedia.count_documents({"isActive": True}), 0)

    async def test_permissions_and_validation(self):
        for role in ["cashier", "admin", "agent", "subagent", "user"]:
            self.role = role
            self.assertEqual((await self.http.get('/admin/site-media')).status_code, 403)
            self.assertEqual((await self.upload()).status_code, 403)
        self.role = 'system'
        self.assertEqual((await self.upload(data=b"x" * (MAX_UPLOAD + 1))).status_code, 413)
        self.assertEqual((await self.upload(data=b"<svg/>" )).status_code, 422)
        self.assertEqual((await self.http.patch('/admin/site-media/undefined', json={"isActive": True})).status_code, 404)
        item = (await self.upload()).json()
        self.assertEqual((await self.http.patch('/admin/site-media/' + item['id'], json={"focalX": 101})).status_code, 422)

    async def test_concurrent_activation(self):
        a = (await self.upload("red", False)).json()
        b = (await self.upload("blue", False)).json()
        replies = await asyncio.gather(*[self.http.patch('/admin/site-media/' + item['id'], json={"isActive": True}) for item in (a, b)])
        self.assertTrue(all(response.status_code in (200, 409) for response in replies))
        self.assertTrue(any(response.status_code == 200 for response in replies))
        self.assertEqual(await self.db.siteMedia.count_documents({"isActive": True}), 1)


if __name__ == '__main__':
    unittest.main()
