"""
Async MongoDB connection management using Motor.

Handles startup/shutdown lifecycle and includes retry logic
for when MongoDB is still booting (common with docker-compose).
"""

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None

MAX_RETRIES = 5
RETRY_BASE_DELAY = 2  # seconds, grows exponentially


async def connect_to_mongo() -> None:
    """Open connection pool to MongoDB, retrying on failure."""
    global _client, _database

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Connecting to MongoDB at %s (attempt %d/%d)...",
                settings.mongo_uri, attempt, MAX_RETRIES,
            )
            _client = AsyncIOMotorClient(
                settings.mongo_uri,
                serverSelectionTimeoutMS=5000,
            )
            await _client.admin.command("ping")
            _database = _client[settings.mongo_db]
            logger.info("Connected to database: %s", settings.mongo_db)
            return

        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error(
                    "Failed to connect after %d attempts: %s",
                    MAX_RETRIES, exc,
                )
                raise
            delay = RETRY_BASE_DELAY ** attempt
            logger.warning(
                "Attempt %d failed (%s) — retrying in %ds...",
                attempt, exc, delay,
            )
            await asyncio.sleep(delay)


async def close_mongo_connection() -> None:
    """Close the Motor client and release pooled connections."""
    global _client, _database

    if _client is not None:
        _client.close()
        _client = None
        _database = None
        logger.info("MongoDB connection closed.")


def get_database() -> AsyncIOMotorDatabase:
    """Return the active database handle. Raises if not connected yet."""
    if _database is None:
        raise RuntimeError(
            "Database not initialised — "
            "make sure connect_to_mongo() ran during startup."
        )
    return _database
