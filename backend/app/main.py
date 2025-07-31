from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from routes import auth,user,game,deposit,withdrawls,creditBalance,addisPayDeposit,addisPayWithdaw,manualDeposit,manualWithdraw
from contextlib import asynccontextmanager
from services.manual_pay import watch_deposit_inserts
from core.db import get_db, get_client

db = get_db()
client = get_client()

#lifecycle events for database connection
@asynccontextmanager
async def lifespan(app: FastAPI):
    #on startup
    task = asyncio.create_task(watch_deposit_inserts(db,client))
    yield
    #on shutdown
    task.cancel()

app = FastAPI(lifespan=lifespan)

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


@app.on_event("startup")


@app.get("/")
async def read_root():
    return {"message": "welcom to hagere online api"}