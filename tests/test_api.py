"""Integration tests for the API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.models.metadata import MetadataDocument
from app.services.collector import CollectorError


def _fake_document(url: str = "https://example.com/") -> MetadataDocument:
    """Helper to create a mock metadata document."""
    return MetadataDocument(
        url=url,
        headers={"content-type": "text/html", "server": "test"},
        cookies=[{"name": "sid", "value": "abc", "domain": "example.com", "path": "/"}],
        page_source="<html><body>Test</body></html>",
        status_code=200,
        collected_at=datetime.now(timezone.utc),
    )


# --- Health ---

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "service" in data


# --- POST /api/v1/metadata ---

@pytest.mark.asyncio
async def test_post_metadata_success(client: AsyncClient):
    with patch("app.api.routes.collect_metadata", new_callable=AsyncMock, return_value=_fake_document()):
        resp = await client.post("/api/v1/metadata", json={"url": "https://example.com"})
    assert resp.status_code == 201
    data = resp.json()
    assert "example.com" in data["url"]
    assert "collected_at" in data


@pytest.mark.asyncio
async def test_post_metadata_invalid_url(client: AsyncClient):
    resp = await client.post("/api/v1/metadata", json={"url": "not-a-url"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_metadata_unreachable_url(client: AsyncClient):
    with patch("app.api.routes.collect_metadata", new_callable=AsyncMock, side_effect=CollectorError("Cannot connect")):
        resp = await client.post("/api/v1/metadata", json={"url": "https://nope.invalid"})
    assert resp.status_code == 400
    assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_post_metadata_missing_body(client: AsyncClient):
    resp = await client.post("/api/v1/metadata")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_metadata_idempotent(client: AsyncClient):
    """Posting the same URL twice should work fine (upsert)."""
    doc = _fake_document()
    with patch("app.api.routes.collect_metadata", new_callable=AsyncMock, return_value=doc):
        r1 = await client.post("/api/v1/metadata", json={"url": "https://example.com"})
        r2 = await client.post("/api/v1/metadata", json={"url": "https://example.com"})
    assert r1.status_code == 201
    assert r2.status_code == 201


# --- GET /api/v1/metadata ---

@pytest.mark.asyncio
async def test_get_metadata_found(client: AsyncClient, seeded_db):
    resp = await client.get("/api/v1/metadata", params={"url": "https://example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["url"] == "https://example.com"
    assert "headers" in data
    assert "cookies" in data
    assert "page_source" in data


@pytest.mark.asyncio
async def test_get_metadata_not_found_returns_202(client: AsyncClient):
    """GET for unknown URL should return 202 and schedule background fetch."""
    with patch("app.api.routes.schedule_background_collection") as mock_bg:
        resp = await client.get("/api/v1/metadata", params={"url": "https://httpbin.org/get"})
    assert resp.status_code == 202
    assert "background collection" in resp.json()["message"].lower()
    mock_bg.assert_called_once()


@pytest.mark.asyncio
async def test_get_metadata_missing_param(client: AsyncClient):
    resp = await client.get("/api/v1/metadata")
    assert resp.status_code == 422


# --- POST -> GET lifecycle ---

@pytest.mark.asyncio
async def test_post_then_get_lifecycle(client: AsyncClient):
    """POST to collect, then GET should return the stored record."""
    doc = _fake_document("https://example.com/")
    with patch("app.api.routes.collect_metadata", new_callable=AsyncMock, return_value=doc):
        post_resp = await client.post("/api/v1/metadata", json={"url": "https://example.com"})
    assert post_resp.status_code == 201

    url = post_resp.json()["url"]
    get_resp = await client.get("/api/v1/metadata", params={"url": url})
    assert get_resp.status_code == 200
    assert len(get_resp.json()["page_source"]) > 0
