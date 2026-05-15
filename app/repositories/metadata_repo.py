"""
MongoDB repository for URL metadata.

Wraps all DB operations behind a clean interface so the rest
of the app doesn't care about MongoDB specifics.
"""

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.metadata import MetadataDocument

logger = logging.getLogger(__name__)

COLLECTION_NAME = "url_metadata"


class MetadataRepository:
    """Async CRUD for the url_metadata collection."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db[COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        """Create a unique index on the url field for fast lookups."""
        await self._collection.create_index(
            "url", unique=True, name="idx_url_unique",
        )
        logger.info("Indexes ensured on '%s'.", COLLECTION_NAME)

    async def find_by_url(self, url: str) -> dict[str, Any] | None:
        """Look up metadata by URL. Returns None if not found."""
        return await self._collection.find_one(
            {"url": url}, {"_id": 0},
        )

    async def insert(self, document: MetadataDocument) -> None:
        """Insert a new metadata document. Raises on duplicate URL."""
        await self._collection.insert_one(document.model_dump())
        logger.info("Inserted metadata for %s", document.url)

    async def upsert(self, document: MetadataDocument) -> None:
        """Insert or replace metadata for a URL (idempotent)."""
        await self._collection.replace_one(
            {"url": document.url},
            document.model_dump(),
            upsert=True,
        )
        logger.info("Upserted metadata for %s", document.url)

    async def delete_by_url(self, url: str) -> bool:
        """Remove a record by URL. Returns True if something was deleted."""
        result = await self._collection.delete_one({"url": url})
        return result.deleted_count > 0
