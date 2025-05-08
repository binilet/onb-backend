from motor.motor_asyncio import AsyncIOMotorClient
from core.config import settings

client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client[settings.MONGODB_NAME]

def get_db():
    return db

def get_client() -> AsyncIOMotorClient:
    return client