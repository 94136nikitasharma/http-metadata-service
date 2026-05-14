"""
Integration tests for the API endpoints.

These tests exercise the full request lifecycle from HTTP request
through to database persistence, using the test fixtures defined
in conftest.py.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models.metadata import MetadataDocument
from app.services.collector import CollectorError


def _mock_document(url: str = "https://example.com/") -> MetadataDocument:
    """Create a mock metadata document for testing."""
    return MetadataDocument(
        url=url,
        headers={"content-type": "text/html", "server": "test"},
        cookies=[{"name": "sid", "value": "abc", "domain": "example.com", "path": "/"}],
        page_source="<html><body>Mocked</body></html>",
        status_code=200,
        collected_at=datetime.now(timezone.utc),
    )


# ════════════════════════ Health Check ═══════════════════════════════════


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """The health endpoint should always return 200 with status info."""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data


# ════════════════════════ POST /api/v1/metadata ═════════════════════════


@pytest.mark.asyncio
async def test_post_metadata_success(client: AsyncClient):
    """
    POST with a valid URL should return 201 with confirmation details.
    """
    mock_doc = _mock_document()

    with patch(
        "app.api.routes.collect_metadata",
        new_callable=AsyncMock,
        return_value=mock_doc,
    ):
        response = await client.post(
            "/api/v1/metadata",
            json={"url": "https://example.com"},
        )

    assert response.status_code == 201
    data = response.json()
    assert "example.com" in data["url"]
    assert "collected_at" in data
    assert "message" in data


@pytest.mark.asyncio
async def test_post_metadata_invalid_url(client: AsyncClient):
    """POST with a malformed URL should return 422 (validation error)."""
    response = await client.post(
        "/api/v1/metadata",
        json={"url": "not-a-valid-url"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_metadata_unreachable_url(client: AsyncClient):
    """POST with a URL that cannot be reached should return 400."""
    with patch(
        "app.api.routes.collect_metadata",
        new_callable=AsyncMock,
        side_effect=CollectorError("Could not connect to URL"),
    ):
        response = await client.post(
            "/api/v1/metadata",
            json={"url": "https://this-domain-does-not-exist-xyz123.com"},
        )

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_post_metadata_missing_body(client: AsyncClient):
    """POST without a request body should return 422."""
    response = await client.post("/api/v1/metadata")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_post_metadata_idempotent(client: AsyncClient):
    """
    Posting the same URL twice should succeed both times (upsert),
    not fail with a duplicate key error.
    """
    mock_doc = _mock_document()

    with patch(
        "app.api.routes.collect_metadata",
        new_callable=AsyncMock,
        return_value=mock_doc,
    ):
        resp1 = await client.post(
            "/api/v1/metadata",
            json={"url": "https://example.com"},
        )
        resp2 = await client.post(
            "/api/v1/metadata",
            json={"url": "https://example.com"},
        )

    assert resp1.status_code == 201
    assert resp2.status_code == 201


# ════════════════════════ GET /api/v1/metadata ══════════════════════════


@pytest.mark.asyncio
async def test_get_metadata_found(client: AsyncClient, seeded_db):
    """
    GET for a URL that exists in the database should return 200
    with the full metadata record.
    """
    response = await client.get(
        "/api/v1/metadata",
        params={"url": "https://example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com"
    assert "headers" in data
    assert "cookies" in data
    assert "page_source" in data
    assert data["status_code"] == 200


@pytest.mark.asyncio
async def test_get_metadata_not_found_returns_202(client: AsyncClient):
    """
    GET for a URL not in the database should return 202 Accepted
    and trigger a background collection.
    """
    with patch(
        "app.api.routes.schedule_background_collection"
    ) as mock_schedule:
        response = await client.get(
            "/api/v1/metadata",
            params={"url": "https://httpbin.org/get"},
        )

    assert response.status_code == 202
    data = response.json()
    assert "background collection" in data["message"].lower()
    assert data["url"] == "https://httpbin.org/get"

    # Verify the background task was scheduled
    mock_schedule.assert_called_once()


@pytest.mark.asyncio
async def test_get_metadata_missing_param(client: AsyncClient):
    """GET without the 'url' query parameter should return 422."""
    response = await client.get("/api/v1/metadata")
    assert response.status_code == 422


# ════════════════════ POST → GET integration ════════════════════════════


@pytest.mark.asyncio
async def test_post_then_get_returns_data(client: AsyncClient):
    """
    End-to-end: POST a URL to collect metadata, then GET should
    return the stored record with status 200.
    """
    mock_doc = _mock_document("https://example.com/")

    with patch(
        "app.api.routes.collect_metadata",
        new_callable=AsyncMock,
        return_value=mock_doc,
    ):
        # Step 1 — collect
        post_resp = await client.post(
            "/api/v1/metadata", json={"url": "https://example.com"}
        )
    assert post_resp.status_code == 201

    # Step 2 — retrieve (Pydantic may normalise the URL with a trailing slash)
    normalised_url = post_resp.json()["url"]
    get_resp = await client.get(
        "/api/v1/metadata", params={"url": normalised_url}
    )

    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["url"] == normalised_url
    assert len(data["page_source"]) > 0
