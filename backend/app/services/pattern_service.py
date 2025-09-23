from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from bson import ObjectId
from datetime import datetime
from schemas.pattern import PatternCreate, PatternUpdate, PatternInDB


class PatternService:

    @staticmethod
    async def get_all(collection: AsyncIOMotorCollection) -> List[PatternInDB]:
        patterns = []
        cursor = collection.find({})
        async for doc in cursor:
            patterns.append(PatternInDB(
                id=str(doc["_id"]),
                name=doc["name"],
                isActive=doc.get("isActive", True),
                grid=doc["grid"],
                created_at=doc["created_at"],
                updated_at=doc["updated_at"]
            ))
        return patterns

    @staticmethod
    async def get_by_id(collection: AsyncIOMotorCollection, pattern_id: str) -> Optional[PatternInDB]:
        doc = await collection.find_one({"_id": ObjectId(pattern_id)})
        if not doc:
            return None
        return PatternInDB(
            id=str(doc["_id"]),
            name=doc["name"],
            isActive=doc.get("isActive", True),
            grid=doc["grid"],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        )

    @staticmethod
    async def create(collection: AsyncIOMotorCollection, pattern: PatternCreate) -> PatternInDB:
        now = datetime.utcnow()
        doc = {
            "name": pattern.name,
            "isActive": pattern.isActive,
            "grid": pattern.grid,
            "created_at": now,
            "updated_at": now
        }
        result = await collection.insert_one(doc)
        return PatternInDB(
            id=str(result.inserted_id),
            **doc
        )

    @staticmethod
    async def update(collection: AsyncIOMotorCollection, pattern_id: str, pattern: PatternUpdate) -> Optional[PatternInDB]:
        update_data = {k: v for k, v in pattern.dict(exclude_unset=True).items()}
        update_data["updated_at"] = datetime.utcnow()

        result = await collection.find_one_and_update(
            {"_id": ObjectId(pattern_id)},
            {"$set": update_data},
            return_document=True  # requires pymongo >= 4.0
        )

        if not result:
            return None

        return PatternInDB(
            id=str(result["_id"]),
            name=result["name"],
            isActive=result.get("isActive", True),
            grid=result["grid"],
            created_at=result["created_at"],
            updated_at=result["updated_at"]
        )
