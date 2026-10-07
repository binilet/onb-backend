from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bson.decimal128 import Decimal128
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.user import UserInDB
from shop.authorization import ADMIN, AGENT, CASHIER, SUBAGENT, SYSTEM, shop_scope_filter
from shop.dashboard import (
    DashboardCutPeriods,
    DashboardOperations,
    DashboardRecentGame,
    DashboardTotals,
    DashboardTrendPoint,
    ShopDashboard,
)
from shop.game_service import game_scope_filter


# Ethiopia has used UTC+03:00 year-round since 1942. A fixed offset keeps the
# service portable on minimal Windows/Linux installations that omit tzdata.
ADDIS_ABABA = timezone(timedelta(hours=3))


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ADDIS_ABABA)


def _and_query(*parts: dict) -> dict:
    active = [part for part in parts if part]
    if not active:
        return {}
    if len(active) == 1:
        return active[0]
    return {"$and": active}


async def _location_scope(db: AsyncIOMotorDatabase, user: UserInDB) -> dict:
    if user.role == SYSTEM:
        return {}
    if user.role in {AGENT, SUBAGENT}:
        shops = await db.shops.find(await shop_scope_filter(db, user), {"shop_id": 1}).to_list(length=None)
        return {"shopId": {"$in": [shop["shop_id"] for shop in shops]}}
    if user.role == ADMIN and user.shopId:
        return {"shopId": user.shopId}
    if user.role == CASHIER and user.shopId and user.branchId:
        return {"shopId": user.shopId, "branchId": user.branchId}
    return {"_id": {"$exists": False}}


async def get_shop_dashboard(
    db: AsyncIOMotorDatabase,
    user: UserInDB,
    start_at: datetime,
    end_at: datetime,
    shop_id: str | None = None,
    branch_id: str | None = None,
) -> ShopDashboard:
    game_scope = await game_scope_filter(db, user)
    location_scope = await _location_scope(db, user)
    selected_location = {
        **({"shopId": shop_id} if shop_id else {}),
        **({"branchId": branch_id} if branch_id else {}),
    }
    period = {"createdAt": {"$gte": start_at, "$lt": end_at}}
    selected_games = _and_query(game_scope, selected_location, period)
    selected_completed = _and_query(selected_games, {"status": "COMPLETE"})
    operational_location = _and_query(location_scope, selected_location)

    completed = await db.games.find(
        selected_completed,
        {
            "_id": 0, "game_id": 1, "gameName": 1, "shopId": 1, "branchId": 1,
            "status": 1, "betAmount": 1, "totalBets": 1, "totalWinning": 1,
            "totalCutAmount": 1, "cartelaCount": 1, "createdAt": 1,
        },
    ).sort("createdAt", 1).to_list(length=None)

    missing_game_ids = [item["game_id"] for item in completed if item.get("totalBets") is None]
    participant_counts = {}
    if missing_game_ids:
        participant_counts = {
            item["_id"]: item["count"]
            async for item in db.gameParticipants.aggregate([
                {"$match": {"gameId": {"$in": missing_game_ids}}},
                {"$group": {"_id": "$gameId", "count": {"$sum": 1}}},
            ])
        }

    totals = DashboardTotals(completedGames=len(completed))
    daily = defaultdict(lambda: {"games": 0, "bets": Decimal("0"), "winnings": Decimal("0"), "cut": Decimal("0")})
    for game in completed:
        cartelas = int(game.get("cartelaCount") or participant_counts.get(game["game_id"], 0))
        bets = _decimal(game.get("totalBets")) if game.get("totalBets") is not None else _decimal(game.get("betAmount")) * cartelas
        winnings = _decimal(game.get("totalWinning"))
        cut = _decimal(game.get("totalCutAmount"))
        totals.totalBets += bets
        totals.totalWinnings += winnings
        totals.totalCut += cut
        totals.cartelasSold += cartelas
        day = _local_datetime(game["createdAt"]).date().isoformat()
        daily[day]["games"] += 1
        daily[day]["bets"] += bets
        daily[day]["winnings"] += winnings
        daily[day]["cut"] += cut

    now = datetime.now(timezone.utc).astimezone(ADDIS_ABABA)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    year = today.replace(month=1, day=1)
    cut_documents = await db.games.find(
        _and_query(game_scope, selected_location, {"status": "COMPLETE", "createdAt": {"$gte": year.astimezone(timezone.utc), "$lt": now.astimezone(timezone.utc)}}),
        {"_id": 0, "createdAt": 1, "totalCutAmount": 1},
    ).to_list(length=None)
    cuts = DashboardCutPeriods()
    for game in cut_documents:
        created = _local_datetime(game["createdAt"])
        amount = _decimal(game.get("totalCutAmount"))
        cuts.year += amount
        if created >= month:
            cuts.month += amount
        if created >= week:
            cuts.week += amount
        if created >= today:
            cuts.today += amount

    status_rows = await db.games.aggregate([
        {"$match": selected_games},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]).to_list(length=None)
    statuses = {status: 0 for status in ("PENDING", "ACTIVE", "COMPLETE", "VOID")}
    statuses.update({str(row["_id"]): row["count"] for row in status_rows if row.get("_id")})

    operations = DashboardOperations(
        pendingGames=await db.games.count_documents(_and_query(game_scope, selected_location, {"status": "PENDING"})),
        activeGames=await db.games.count_documents(_and_query(game_scope, selected_location, {"status": "ACTIVE"})),
        pendingDeposits=await db.shopDeposits.count_documents(_and_query(operational_location, {"status": {"$in": ["PENDING", "FAILED"]}})),
        pendingWithdrawals=await db.shopWithdrawals.count_documents(_and_query(operational_location, {"status": {"$in": ["PENDING", "CASH_DISBURSED", "PLAYER_CONFIRMED"]}})),
    )

    balance = await db.shopBalances.find_one({"phone": user.phone}, {"currentBalance": 1})
    recent_documents = await db.games.find(selected_games, {
        "_id": 0, "game_id": 1, "gameName": 1, "shopId": 1, "branchId": 1,
        "status": 1, "betAmount": 1, "totalBets": 1, "totalWinning": 1,
        "totalCutAmount": 1, "createdAt": 1,
    }).sort("createdAt", -1).limit(8).to_list(length=8)

    recent = []
    for game in recent_documents:
        recent.append(DashboardRecentGame(
            gameId=game["game_id"], gameName=game.get("gameName") or f"Game {game['game_id'][:8].upper()}",
            shopId=game["shopId"], branchId=game["branchId"], status=game.get("status", "PENDING"),
            betAmount=_decimal(game.get("betAmount")), totalBets=_decimal(game.get("totalBets")),
            totalWinning=_decimal(game.get("totalWinning")), totalCutAmount=_decimal(game.get("totalCutAmount")),
            createdAt=game["createdAt"],
        ))

    trend = [DashboardTrendPoint(date=day, **values) for day, values in sorted(daily.items())]
    return ShopDashboard(
        startAt=start_at, endAt=end_at, currentBalance=_decimal(balance.get("currentBalance")) if balance else Decimal("0"),
        totals=totals, cuts=cuts, operations=operations, gameStatuses=statuses,
        trend=trend, recentGames=recent, shopId=shop_id, branchId=branch_id,
    )
