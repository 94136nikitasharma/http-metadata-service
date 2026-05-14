"""
Unit tests for the metadata repository.

These tests run against a real (test) MongoDB instance to verify
CRUD operations, index behaviour, and edge cases at the data layer.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.models.metadata import MetadataDocument
from app.repositories.metadata_repo import MetadataRepository

TEST_DB_NAME = "metadata_inventory_repo_test"


@pytest_asyncio.fixture()
async def repo():
    """Provide a repository backed by a clean test database."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[TEST_DB_NAME]
    repository = MetadataRepository(db)
    await repository.ensure_indexes()

    yield repository

    await client.drop_database(TEST_DB_NAME)
    client.close()


def _sample_document(url: str = "https://example.com") -> MetadataDocument:
    """Create a sample metadata document for testing."""
    return MetadataDocument(
        url=url,
        headers={"content-type": "text/html"},
        cookies=[{"name": "test", "value": "123", "domain": "example.com", "path": "/"}],
        page_source="<html><body>Test</body></html>",
        status_code=200,
        collected_at=datetime.now(timezone.utc),
    )


# ════════════════════════ Insert & Find ═════════════════════════════════


@pytest.mark.asyncio
async def test_insert_and_find(repo: MetadataRepository):
    """Inserted document should be retrievable by URL."""
    doc = _sample_document()
    await repo.insert(doc)

    result = await repo.find_by_url("https://example.com")

    assert result is not None
    assert result["url"] == "https://example.com"
    assert result["status_code"] == 200
    assert len(result["cookies"]) == 1


@pytest.mark.asyncio
async def test_find_nonexistent_returns_none(repo: MetadataRepository):
    """Looking up a URL that was never stored should return None."""
    result = await repo.find_by_url("https://does-not-exist.com")
    assert result is None


# ════════════════════════ Upsert ════════════════════════════════════════


@pytest.mark.asyncio
async def test_upsert_creates_new(repo: MetadataRepository):
    """Upsert should create a document if it doesn't exist."""
    doc = _sample_document("https://new-site.com")
    await repo.upsert(doc)

    result = await repo.find_by_url("https://new-site.com")
    assert result is not None
    assert result["url"] == "https://new-site.com"


@pytest.mark.asyncio
async def test_upsert_updates_existing(repo: MetadataRepository):
    """Upsert should overwrite an existing document for the same URL."""
    doc1 = _sample_document()
    doc1.page_source = "original"
    await repo.upsert(doc1)

    doc2 = _sample_document()
    doc2.page_source = "updated"
    await repo.upsert(doc2)

    result = await repo.find_by_url("https://example.com")
    assert result is not None
    assert result["page_source"] == "updated"


# ════════════════════════ Delete ════════════════════════════════════════


@pytest.mark.asyncio
async def test_delete_existing(repo: MetadataRepository):
    """Deleting an existing URL should return True and remove the record."""
    doc = _sample_document()
    await repo.insert(doc)

    deleted = await repo.delete_by_url("https://example.com")
    assert deleted is True

    result = await repo.find_by_url("https://example.com")
    assert result is None


@pytest.mark.asyncio
async def test_delete_nonexistent(repo: MetadataRepository):
    """Deleting a non-existent URL should return False."""
    deleted = await repo.delete_by_url("https://ghost.com")
    assert deleted is False


# ════════════════════════ Index ═════════════════════════════════════════


@pytest.mark.asyncio
async def test_ensure_indexes_idempotent(repo: MetadataRepository):
    """Calling ensure_indexes multiple times should not raise errors."""
    await repo.ensure_indexes()
    await repo.ensure_indexes()
    # No assertion needed — success means no exception was raised
