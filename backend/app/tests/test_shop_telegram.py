"""Shop Telegram settings endpoints. Uses mongomock-motor, so no database is needed.

Run from backend/app: python -m unittest tests.test_shop_telegram
(needs `pip install mongomock-motor httpx`; skipped otherwise).
"""
import asyncio
import os
import unittest

os.environ.setdefault("MONGODB_URL", "mongodb://127.0.0.1:1")
os.environ.setdefault("SECRET_KEY", "test-secret")

try:
    from mongomock_motor import AsyncMongoMockClient
    from fastapi.testclient import TestClient
except ImportError:  # optional test dependencies
    AsyncMongoMockClient = None

from fastapi import FastAPI

from core.config import settings
from core.db import get_db
from dependencies.auth import get_current_active_user
from models.user import UserInDB
from shop.telegram import CODE_ALPHABET, router


def make_user(role, **extra):
    return UserInDB(**{"_id": "u1", "phone": "0911000000", "username": "tester", "role": role, "password": "secret123", **extra})


@unittest.skipIf(AsyncMongoMockClient is None, "mongomock-motor and httpx are not installed")
class ShopTelegramTests(unittest.TestCase):
    def setUp(self):
        self.db = AsyncMongoMockClient()["shop_telegram_test"]
        self.user = make_user("system")
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_active_user] = lambda: self.user
        self.client = TestClient(app)
        self._bot = settings.SHOP_TELEGRAM_BOT_USERNAME
        settings.SHOP_TELEGRAM_BOT_USERNAME = "@HagereBingoBot"
        self.run_async(self.db.shops.insert_many([
            {"shop_id": "s1", "shopName": "Abebe <Shop>", "agentId": "0911000000", "representativePhone": "0911000000",
             "telegram": {"deposits": {"chatId": "-100", "threadId": 4, "status": "BROKEN", "lastError": "kicked"}}},
            {"shop_id": "s2", "shopName": "Other", "agentId": "0922000000", "representativePhone": "0922000000"},
        ]))

    def tearDown(self):
        settings.SHOP_TELEGRAM_BOT_USERNAME = self._bot

    @staticmethod
    def run_async(awaitable):
        return asyncio.run(awaitable)

    def test_settings_view(self):
        body = self.client.get("/api/shop/shops/s1/telegram").json()
        self.assertEqual(body["botUsername"], "HagereAlertsBot")
        self.assertEqual(body["deposits"]["threadId"], 4)
        self.assertEqual(body["deposits"]["status"], "BROKEN")
        self.assertIsNone(body["general"])

    def test_link_code_replaces_the_previous_one(self):
        self.client.post("/api/shop/shops/s1/telegram/withdrawals/link-code")
        response = self.client.post("/api/shop/shops/s1/telegram/withdrawals/link-code")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["code"][4], "-")
        self.assertEqual(body["command"], f"/link {body['code']}")
        codes = self.run_async(self.db.telegramLinkCodes.find({}).to_list(None))
        self.assertEqual([code["code"] for code in codes], [body["code"].replace("-", "")])
        self.assertIsNone(codes[0]["usedAt"])
        self.assertFalse(set(codes[0]["code"]) - set(CODE_ALPHABET))

    def test_unknown_target_is_rejected(self):
        self.assertEqual(self.client.post("/api/shop/shops/s1/telegram/nope/link-code").status_code, 422)

    def test_test_message_needs_a_link_and_is_escaped(self):
        self.assertEqual(self.client.post("/api/shop/shops/s1/telegram/general/test").status_code, 409)
        self.assertEqual(self.client.post("/api/shop/shops/s1/telegram/deposits/test").status_code, 202)
        row = self.run_async(self.db.telegramOutbox.find_one({}))
        self.assertTrue(row["dedupeKey"].startswith("test:"))
        self.assertEqual((row["status"], row["target"]), ("PENDING", "deposits"))
        self.assertIn("Abebe &lt;Shop&gt;", row["text"])

    def test_unlink(self):
        response = self.client.delete("/api/shop/shops/s1/telegram/deposits")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["deposits"])

    def test_scope(self):
        self.user = make_user("cashier", shopId="s1", branchId="b1")
        self.assertEqual(self.client.get("/api/shop/shops/s1/telegram").status_code, 403)
        self.user = make_user("admin", shopId="s1")
        self.assertEqual(self.client.get("/api/shop/shops/s1/telegram").status_code, 200)
        # A shop admin must not reach another shop by changing the id.
        self.assertEqual(self.client.get("/api/shop/shops/s2/telegram").status_code, 404)


if __name__ == "__main__":
    unittest.main()
