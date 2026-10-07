"""Dashboard aggregation tests against the disposable local replica set."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from uuid import uuid4

from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorClient

from shop.dashboard_service import get_shop_dashboard


class ShopDashboardTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncIOMotorClient("mongodb://127.0.0.1:27017/?replicaSet=rs0", serverSelectionTimeoutMS=3000)
        self.db_name = f"codex_shop_dashboard_{uuid4().hex}"
        self.db = self.client[self.db_name]
        await self.client.admin.command("ping")
        for name in ("games", "gameParticipants", "shopBalances", "shopDeposits", "shopWithdrawals", "shops"):
            await self.db.create_collection(name)
        self.now = datetime.now(timezone.utc)
        self.user = SimpleNamespace(role="system", phone="system", shopId=None, branchId=None)
        await self.db.shopBalances.insert_one({"phone": "system", "currentBalance": Decimal128("425.50")})
        await self.db.games.insert_many([
            {
                "game_id": "complete-1", "gameName": "Morning", "shopId": "s1", "branchId": "b1",
                "createdByPhone": "cashier-1", "status": "COMPLETE", "betAmount": Decimal128("10"),
                "totalBets": Decimal128("50"), "cartelaCount": 5, "totalWinning": Decimal128("45"),
                "totalCutAmount": Decimal128("5"), "createdAt": self.now,
            },
            {
                "game_id": "complete-legacy", "gameName": "Legacy", "shopId": "s1", "branchId": "b1",
                "createdByPhone": "cashier-1", "status": "COMPLETE", "betAmount": Decimal128("20"),
                "totalWinning": Decimal128("36"), "totalCutAmount": Decimal128("4"), "createdAt": self.now,
            },
            {
                "game_id": "pending-1", "gameName": "Next", "shopId": "s1", "branchId": "b1",
                "createdByPhone": "cashier-1", "status": "PENDING", "betAmount": Decimal128("10"),
                "createdAt": self.now,
            },
        ])
        await self.db.gameParticipants.insert_many([
            {"gameId": "complete-legacy", "playerPhone": "p1"},
            {"gameId": "complete-legacy", "playerPhone": "p2"},
        ])
        await self.db.shopDeposits.insert_one({"shopId": "s1", "branchId": "b1", "status": "FAILED"})
        await self.db.shopWithdrawals.insert_one({"shopId": "s1", "branchId": "b1", "status": "PLAYER_CONFIRMED"})

    async def asyncTearDown(self):
        self.assertRegex(self.db_name, r"^codex_shop_dashboard_[0-9a-f]{32}$")
        await self.client.drop_database(self.db_name)
        self.client.close()

    async def test_totals_use_persisted_and_legacy_cartela_counts(self):
        result = await get_shop_dashboard(
            self.db, self.user, self.now - timedelta(days=1), self.now + timedelta(days=1), "s1", "b1",
        )
        self.assertEqual(result.currentBalance, Decimal("425.50"))
        self.assertEqual(result.totals.completedGames, 2)
        self.assertEqual(result.totals.totalBets, Decimal("90"))
        self.assertEqual(result.totals.totalWinnings, Decimal("81"))
        self.assertEqual(result.totals.totalCut, Decimal("9"))
        self.assertEqual(result.totals.cartelasSold, 7)
        self.assertEqual(result.operations.pendingGames, 1)
        self.assertEqual(result.operations.pendingDeposits, 1)
        self.assertEqual(result.operations.pendingWithdrawals, 1)
        self.assertEqual(result.gameStatuses["COMPLETE"], 2)
        self.assertEqual(len(result.recentGames), 3)

    async def test_selected_shop_cannot_include_other_shop(self):
        await self.db.games.insert_one({
            "game_id": "other", "gameName": "Other", "shopId": "s2", "branchId": "b2",
            "createdByPhone": "cashier-2", "status": "COMPLETE", "betAmount": Decimal128("100"),
            "totalBets": Decimal128("1000"), "cartelaCount": 10, "totalWinning": Decimal128("900"),
            "totalCutAmount": Decimal128("100"), "createdAt": self.now,
        })
        result = await get_shop_dashboard(
            self.db, self.user, self.now - timedelta(days=1), self.now + timedelta(days=1), "s1", None,
        )
        self.assertEqual(result.totals.totalCut, Decimal("9"))

    async def test_admin_cannot_expand_dashboard_outside_assigned_shop(self):
        admin = SimpleNamespace(role="admin", phone="admin-1", shopId="s1", branchId=None)
        result = await get_shop_dashboard(
            self.db, admin, self.now - timedelta(days=1), self.now + timedelta(days=1), "s2", None,
        )
        self.assertEqual(result.totals.completedGames, 0)
        self.assertEqual(result.operations.pendingGames, 0)
