"""Repository tests — runs against a real (test) MongoDB instance."""

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
    """Clean test DB with indexes ready."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[TEST_DB_NAME]
    repository = MetadataRepository(db)
    await repository.ensure_indexes()
    yield repository
    await client.drop_database(TEST_DB_NAME)
    client.close()


def _sample_doc(url="https://example.com") -> MetadataDocument:
    return MetadataDocument(
        url=url,
        headers={"content-type": "text/html"},
        cookies=[{"name": "test", "value": "123", "domain": "example.com", "path": "/"}],
        page_source="<html><body>Test</body></html>",
        status_code=200,
        collected_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_insert_and_find(repo):
    doc = _sample_doc()
    await repo.insert(doc)
    result = await repo.find_by_url("https://example.com")
    assert result is not None
    assert result["url"] == "https://example.com"
    assert result["status_code"] == 200
    assert len(result["cookies"]) == 1


@pytest.mark.asyncio
async def test_find_nonexistent_returns_none(repo):
    result = await repo.find_by_url("https://does-not-exist.com")
    assert result is None


@pytest.mark.asyncio
async def test_upsert_creates_new(repo):
    doc = _sample_doc("https://new-site.com")
    await repo.upsert(doc)
    result = await repo.find_by_url("https://new-site.com")
    assert result is not None


@pytest.mark.asyncio
async def test_upsert_updates_existing(repo):
    """Upserting same URL should overwrite the old data."""
    doc1 = _sample_doc()
    doc1.page_source = "original"
    await repo.upsert(doc1)

    doc2 = _sample_doc()
    doc2.page_source = "updated"
    await repo.upsert(doc2)

    result = await repo.find_by_url("https://example.com")
    assert result["page_source"] == "updated"


@pytest.mark.asyncio
async def test_delete_existing(repo):
    await repo.insert(_sample_doc())
    assert await repo.delete_by_url("https://example.com") is True
    assert await repo.find_by_url("https://example.com") is None


@pytest.mark.asyncio
async def test_delete_nonexistent(repo):
    assert await repo.delete_by_url("https://ghost.com") is False


@pytest.mark.asyncio
async def test_ensure_indexes_idempotent(repo):
    """Calling ensure_indexes multiple times shouldn't break anything."""
    await repo.ensure_indexes()
    await repo.ensure_indexes()
