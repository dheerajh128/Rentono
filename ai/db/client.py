"""
MongoDB async client using Motor.
Provides connection to the shared database used by the Node.js app.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from ai.config import get_settings

settings = get_settings()



class MongoClient:
    """Singleton MongoDB client manager."""
    
    _client: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    async def get_client(cls) -> AsyncIOMotorClient:
        """Get or create the MongoDB client."""
        if cls._client is None:
            settings = get_settings()
            cls._client = AsyncIOMotorClient(
                settings.ATLAS_URL,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
        return cls._client
    
    @classmethod
    async def get_database(cls) -> AsyncIOMotorDatabase:
        """Get the database instance."""
        if cls._db is None:
            client = await cls.get_client()
            # Extract database name from connection string or use default
            settings = get_settings()
            # The Atlas URL format includes the database in the path
            cls._db = client[settings.DB_NAME]
        return cls._db
    
    @classmethod
    async def close(cls):
        """Close the MongoDB connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None


async def get_db() -> AsyncIOMotorDatabase:
    """
    Convenience function to get the database instance.
    Use this in services and repositories.
    """
    return await MongoClient.get_database()


async def test_connection() -> bool:
    """
    Test the MongoDB connection.
    Returns True if successful, raises exception otherwise.
    """
    try:
        db = await get_db()
        # Ping the database
        await db.command("ping")
        return True
    except Exception as e:
        raise RuntimeError(f"Failed to connect to MongoDB: {e}") from e
