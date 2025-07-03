from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import auth,user,game,deposit,withdrawls,creditBalance,addisPayDeposit
app = FastAPI()

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

@app.get("/")
async def read_root():
    return {"message": "welcom to hagere online api"}