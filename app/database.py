"""
Asynchronous MongoDB connection management using Motor.

Provides lifecycle helpers that are called during FastAPI's startup
and shutdown events to ensure connections are properly established
and released.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level references, initialised during application startup
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_to_mongo() -> None:
    """
    Open a connection pool to MongoDB.

    Called once during application startup. The Motor client manages
    an internal connection pool, so a single client instance is reused
    across the entire application lifetime.
    """
    global _client, _database

    logger.info("Connecting to MongoDB at %s ...", settings.mongo_uri)
    _client = AsyncIOMotorClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=5000,
    )

    # Verify the connection is alive
    await _client.admin.command("ping")
    _database = _client[settings.mongo_db]
    logger.info("Connected to MongoDB — database: %s", settings.mongo_db)


async def close_mongo_connection() -> None:
    """Close the Motor client, releasing all pooled connections."""
    global _client, _database

    if _client is not None:
        _client.close()
        _client = None
        _database = None
        logger.info("MongoDB connection closed.")


def get_database() -> AsyncIOMotorDatabase:
    """
    Return the active database handle.

    Raises RuntimeError if called before the connection has been
    established (i.e. before application startup completes).
    """
    if _database is None:
        raise RuntimeError(
            "Database is not initialised. "
            "Ensure connect_to_mongo() has been called during startup."
        )
    return _database
