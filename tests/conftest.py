"""Shared pytest fixtures — test DB, app client, seed data."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.main import app

pytest_plugins = ("pytest_asyncio",)

TEST_DB_NAME = "metadata_inventory_test"


@pytest_asyncio.fixture()
async def test_db():
    """Spin up a clean test database, tear it down after."""
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[TEST_DB_NAME]
    await client.drop_database(TEST_DB_NAME)

    yield db

    await client.drop_database(TEST_DB_NAME)
    client.close()


@pytest_asyncio.fixture()
async def client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the test app with patched DB."""
    import app.database as db_module
    from app.repositories.metadata_repo import MetadataRepository

    original_db = db_module._database
    db_module._database = test_db

    # Make sure indexes exist on the test DB
    repo = MetadataRepository(test_db)
    await repo.ensure_indexes()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    db_module._database = original_db


@pytest_asyncio.fixture()
async def seeded_db(test_db):
    """Pre-populate the test DB with a known document."""
    from app.repositories.metadata_repo import MetadataRepository

    repo = MetadataRepository(test_db)
    await repo.ensure_indexes()

    doc = {
        "url": "https://example.com",
        "headers": {"content-type": "text/html; charset=UTF-8"},
        "cookies": [
            {"name": "session_id", "value": "abc123", "domain": "example.com", "path": "/"}
        ],
        "page_source": "<html><body>Hello</body></html>",
        "status_code": 200,
        "collected_at": datetime.now(timezone.utc),
    }
    await test_db["url_metadata"].insert_one(doc.copy())
    return doc
