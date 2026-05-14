"""
Shared pytest fixtures and configuration.

The fixtures provide:
  - An isolated test MongoDB database (automatically cleaned up).
  - A pre-configured ``AsyncClient`` wired to the FastAPI test app.
  - Helpers to seed the database with known documents.
"""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.main import app

# Use the same event loop for all async tests in the session
pytest_plugins = ("pytest_asyncio",)


# ──────────────────────────── Event Loop ────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ──────────────────────────── Database ──────────────────────────────────

TEST_DB_NAME = "metadata_inventory_test"


@pytest_asyncio.fixture()
async def test_db():
    """
    Provide a clean test database for each test.

    Creates a fresh database before the test, yields the database
    handle, and drops the database after the test completes.
    """
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[TEST_DB_NAME]

    yield db

    # Teardown — drop the test database to ensure isolation
    await client.drop_database(TEST_DB_NAME)
    client.close()


# ──────────────────────── Application Client ────────────────────────────


@pytest_asyncio.fixture()
async def client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP client connected to the FastAPI test app.

    Patches the database module to use the test database so that
    tests run against an isolated environment.
    """
    # Monkey-patch the database getter to return our test DB
    import app.database as db_module

    original_get_db = db_module.get_database
    db_module.get_database = lambda: test_db

    # Ensure indexes on the test database
    from app.repositories.metadata_repo import MetadataRepository

    repo = MetadataRepository(test_db)
    await repo.ensure_indexes()

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as ac:
        yield ac

    # Restore original
    db_module.get_database = original_get_db


# ──────────────────────── Seed Helpers ──────────────────────────────────


@pytest_asyncio.fixture()
async def seeded_db(test_db):
    """
    Pre-populate the test database with a known metadata document.

    Returns the seeded document dict for assertions.
    """
    doc = {
        "url": "https://example.com",
        "headers": {"content-type": "text/html; charset=UTF-8"},
        "cookies": [
            {
                "name": "session_id",
                "value": "abc123",
                "domain": "example.com",
                "path": "/",
            }
        ],
        "page_source": "<html><body>Hello</body></html>",
        "status_code": 200,
        "collected_at": datetime.now(timezone.utc),
    }
    await test_db["url_metadata"].insert_one(doc.copy())

    # Also ensure the unique index exists
    await test_db["url_metadata"].create_index("url", unique=True)

    return doc
