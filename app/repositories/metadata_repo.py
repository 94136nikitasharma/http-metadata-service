"""
MongoDB repository for URL metadata documents.

Encapsulates all database operations behind a clean interface,
keeping the rest of the application agnostic to storage details.
This makes it straightforward to swap the persistence backend
(e.g. to PostgreSQL) or add caching in the future.
"""

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.metadata import MetadataDocument

logger = logging.getLogger(__name__)

COLLECTION_NAME = "url_metadata"


class MetadataRepository:
    """
    Async CRUD interface for the ``url_metadata`` collection.

    Parameters
    ----------
    db : AsyncIOMotorDatabase
        An active Motor database handle (provided via dependency injection).
    """

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db[COLLECTION_NAME]

    # ── Index management ────────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """
        Create indexes required for efficient queries.

        A unique index on ``url`` guarantees fast lookups and prevents
        duplicate records for the same URL.
        """
        await self._collection.create_index(
            "url",
            unique=True,
            name="idx_url_unique",
        )
        logger.info("Database indexes ensured on '%s'.", COLLECTION_NAME)

    # ── Read ────────────────────────────────────────────────────────

    async def find_by_url(self, url: str) -> dict[str, Any] | None:
        """
        Look up a metadata record by its URL.

        Returns the raw MongoDB document (without ``_id``) or ``None``
        if the URL has not been collected yet.
        """
        document = await self._collection.find_one(
            {"url": url},
            {"_id": 0},  # exclude Mongo's internal ID from the result
        )
        return document

    # ── Write ───────────────────────────────────────────────────────

    async def insert(self, document: MetadataDocument) -> None:
        """
        Insert a new metadata document.

        Raises ``pymongo.errors.DuplicateKeyError`` if the URL already
        exists (callers should handle or use :meth:`upsert` instead).
        """
        await self._collection.insert_one(document.model_dump())
        logger.info("Inserted metadata for %s", document.url)

    async def upsert(self, document: MetadataDocument) -> None:
        """
        Insert or update a metadata document for the given URL.

        Uses MongoDB's ``replace_one`` with ``upsert=True`` to ensure
        idempotent writes — safe to call from background tasks without
        worrying about race conditions with the POST endpoint.
        """
        await self._collection.replace_one(
            {"url": document.url},
            document.model_dump(),
            upsert=True,
        )
        logger.info("Upserted metadata for %s", document.url)

    # ── Delete (utility) ───────────────────────────────────────────

    async def delete_by_url(self, url: str) -> bool:
        """
        Remove a metadata record by URL.

        Returns ``True`` if a document was deleted, ``False`` otherwise.
        """
        result = await self._collection.delete_one({"url": url})
        return result.deleted_count > 0
