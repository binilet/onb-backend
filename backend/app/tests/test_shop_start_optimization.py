"""Local replica-set tests; never uses the application's configured database."""
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch
from uuid import uuid4

from bson.decimal128 import Decimal128
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

from shop import game_service
from shop.games import ShopGame, GameLifecycleRequest


class ShopStartTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncIOMotorClient("mongodb://127.0.0.1:27017/?replicaSet=rs0", serverSelectionTimeoutMS=3000)
        self.db_name = f"codex_shop_start_{uuid4().hex}"
        self.db = self.client[self.db_name]
        await self.client.admin.command("ping")
        for name in ("games", "gameParticipants", "shopBalances", "shopBalanceLedgers"):
            await self.db.create_collection(name)
        self.user = SimpleNamespace(role="system", phone="test-system")
        self.game = ShopGame(shopId="test-shop", branchId="test-branch", gameName="Test game",
            betAmount=Decimal("10"), totalCutPercent=Decimal("10"), dynamicPattern="any_line", createdByPhone="test-cashier")
        document = self.game.model_dump(exclude={"cartelaCount", "totalBets"})
        for key, value in document.items():
            if isinstance(value, Decimal):
                document[key] = Decimal128(value)
        await self.db.games.insert_one(document)
        await self.db.shopBalances.insert_one({"phone": "test-cashier", "currentBalance": Decimal128("100")})

    async def asyncTearDown(self):
        self.assertRegex(self.db_name, r"^codex_shop_start_[0-9a-f]{32}$")
        await self.client.drop_database(self.db_name)
        self.client.close()

    async def participants(self, phones):
        await self.db.gameParticipants.insert_many([
            {"gameId": self.game.game_id, "cartelaId": str(i), "playerPhone": phone}
            for i, phone in enumerate(phones)
        ])

    async def start_game(self):
        async def scoped(*args):
            return game_service._game_from_document(await self.db.games.find_one({"game_id": self.game.game_id}))
        with patch.object(game_service, "get_scoped_shop_game", side_effect=scoped):
            return await game_service.apply_game_lifecycle_action(
                self.db, self.user, self.game.game_id, GameLifecycleRequest(action="START"))

    async def test_start_locks_final_pool_and_debits_creator_once(self):
        await self.participants(["one", "two", "two"])
        before = datetime.now(timezone.utc)
        result = await self.start_game()
        self.assertTrue(result.isPurchaseLocked)
        self.assertEqual(result.totalWinning, Decimal("27"))
        self.assertEqual(result.totalCutAmount, Decimal("3"))
        self.assertGreaterEqual((result.scheduledStartAt.replace(tzinfo=timezone.utc) - before).total_seconds(), 20)
        await self.start_game()
        balance = await self.db.shopBalances.find_one({"phone": "test-cashier"})
        self.assertEqual(balance["currentBalance"].to_decimal(), Decimal("97"))
        self.assertEqual(await self.db.shopBalanceLedgers.count_documents({}), 1)

    async def test_insufficient_balance_rolls_back_purchase_lock(self):
        await self.participants(["one", "two"])
        await self.db.shopBalances.update_one({}, {"$set": {"currentBalance": Decimal128("0")}})
        with self.assertRaises(HTTPException) as raised:
            await self.start_game()
        self.assertEqual(raised.exception.status_code, 409)
        game = await self.db.games.find_one({"game_id": self.game.game_id})
        self.assertFalse(game["isPurchaseLocked"])
        self.assertEqual(await self.db.shopBalanceLedgers.count_documents({}), 0)

    async def test_one_player_rolls_back_lock(self):
        await self.participants(["one", "one"])
        with self.assertRaises(HTTPException) as raised:
            await self.start_game()
        self.assertEqual(raised.exception.detail["code"], "WAITING_FOR_PLAYERS")
        self.assertFalse((await self.db.games.find_one({}))["isPurchaseLocked"])

    async def test_fixed_pool_is_preserved(self):
        await self.participants(["one", "two"])
        await self.db.games.update_one({}, {"$set": {"totalWinning": Decimal128("1000")}})
        self.assertEqual((await self.start_game()).totalWinning, Decimal("1000"))

    async def test_transient_conflict_is_retryable_409(self):
        async with await self.client.start_session() as session:
            with self.assertRaises(HTTPException) as raised:
                async with game_service._start_transaction(session):
                    raise OperationFailure("Write conflict", 112, {"errorLabels": ["TransientTransactionError"]})
        self.assertEqual(raised.exception.status_code, 409)
