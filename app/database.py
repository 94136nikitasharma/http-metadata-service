"""
Asynchronous MongoDB connection management using Motor.

Provides lifecycle helpers that are called during FastAPI's startup
and shutdown events to ensure connections are properly established
and released.

Includes retry logic with exponential backoff to handle scenarios
where MongoDB may still be initialising (common in containerised
environments where the API starts before the database is fully ready).
"""

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level references, initialised during application startup
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None

# Retry configuration for startup connection
MAX_RETRIES = 5
RETRY_BASE_DELAY = 2  # seconds — grows exponentially


async def connect_to_mongo() -> None:
    """
    Open a connection pool to MongoDB with retry logic.

    Called once during application startup. Retries with exponential
    backoff if the initial connection attempt fails — this handles the
    common Docker Compose race condition where the API container starts
    before MongoDB has finished initialising.
    """
    global _client, _database

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "Connecting to MongoDB at %s (attempt %d/%d) ...",
                settings.mongo_uri,
                attempt,
                MAX_RETRIES,
            )
            _client = AsyncIOMotorClient(
                settings.mongo_uri,
                serverSelectionTimeoutMS=5000,
            )

            # Verify the connection is alive
            await _client.admin.command("ping")
            _database = _client[settings.mongo_db]
            logger.info(
                "Connected to MongoDB — database: %s", settings.mongo_db
            )
            return

        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.error(
                    "Failed to connect to MongoDB after %d attempts: %s",
                    MAX_RETRIES,
                    exc,
                )
                raise

            delay = RETRY_BASE_DELAY ** attempt
            logger.warning(
                "MongoDB connection attempt %d failed: %s — "
                "retrying in %ds ...",
                attempt,
                exc,
                delay,
            )
            await asyncio.sleep(delay)


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
