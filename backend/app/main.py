from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from routes import auth,user,game,deposit,withdrawls,creditBalance,addisPayDeposit,addisPayWithdaw,manualDeposit,manualWithdraw,pattern,autoGameRoute
from shop.router import router as shop_router
from routes.site_media import router as site_media_router, ensure_indexes as ensure_media_indexes, MediaUploadLimit
from services.site_media import media_root, media_url_base
from fastapi.staticfiles import StaticFiles
from shop.telegram import router as shop_telegram_router
from contextlib import asynccontextmanager
from services.manual_pay import watch_deposit_inserts
from core.winningDistribution import periodic_auto_distribute
from core.db import get_db, get_client
from core.config import settings

db = get_db()
client = get_client()

#lifecycle events for database connection
@asynccontextmanager
async def lifespan(app: FastAPI):
    #on startup
    media_url_base()
    await ensure_media_indexes(db)
    # Preserve existing Shop staff when introducing explicit shop membership.
    # New legacy accounts default to ``forShop: false`` and are never changed here.
    await db.users.update_many(
        {"forShop": {"$exists": False}, "role": {"$in": ["agent", "subagent", "admin", "cashier"]}},
        {"$set": {"forShop": True}},
    )
    deposit_task  = asyncio.create_task(watch_deposit_inserts(db,client))
    auto_dist_task = asyncio.create_task(periodic_auto_distribute(db_client=client,interval_seconds=settings.AUTO_DISTRIBUTE_INTERVAL_SECONDS))
    yield
    #on shutdown
    deposit_task .cancel()
    auto_dist_task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(MediaUploadLimit)
# Development preview only. Production serves this directory through nginx.
if not settings.IS_PRODUCTION:
    (media_root() / "site-media").mkdir(parents=True, exist_ok=True)
    app.mount("/media/site-media", StaticFiles(directory=media_root() / "site-media"), name="site-media-files")

#cors middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

#include routes
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(game.router)
app.include_router(deposit.router)
app.include_router(withdrawls.router)
app.include_router(creditBalance.router)
app.include_router(addisPayDeposit.router)
app.include_router(addisPayWithdaw.router)
app.include_router(manualDeposit.router)
app.include_router(manualWithdraw.router)
app.include_router(pattern.router)
app.include_router(autoGameRoute.router)
app.include_router(shop_router)
app.include_router(site_media_router)
app.include_router(site_media_router, prefix="/api", include_in_schema=False)
app.include_router(shop_telegram_router)


@app.on_event("startup")


@app.get("/")
async def read_root():
    return {"message": "welcom to hagere online api"}


# Utility to list routes
@app.on_event("startup")
async def list_routes():
    for route in app.routes:
        if hasattr(route, "methods"):
            methods = ",".join(route.methods)
            print(f"{methods:10s} {route.path}")
