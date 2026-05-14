"""
Unit tests for the HTTP metadata collector service.

These tests mock the external HTTP layer (httpx) to verify the
collector's parsing logic, error handling, and edge cases without
making real network requests.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.collector import CollectorError, collect_metadata


def _build_mock_response(
    status_code: int = 200,
    headers: dict | None = None,
    text: str = "<html><body>Test</body></html>",
    cookies: list[tuple[str, str]] | None = None,
) -> MagicMock:
    """
    Build a mock httpx.Response with the specified attributes.
    """
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = httpx.Headers(headers or {"content-type": "text/html"})
    response.text = text

    # Build a mock cookie jar
    jar = MagicMock()
    mock_cookies = []
    for name, value in (cookies or []):
        c = MagicMock()
        c.name = name
        c.value = value
        c.domain = "example.com"
        c.path = "/"
        mock_cookies.append(c)
    jar.__iter__ = lambda self: iter(mock_cookies)
    response.cookies.jar = mock_cookies

    return response


# ════════════════════════ Success Cases ═════════════════════════════════


@pytest.mark.asyncio
async def test_collect_metadata_success():
    """Collector should parse headers, cookies, and page source correctly."""
    mock_response = _build_mock_response(
        status_code=200,
        headers={"content-type": "text/html", "server": "nginx"},
        text="<html><body>Hello World</body></html>",
        cookies=[("session", "abc123")],
    )

    with patch("app.services.collector.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_response
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await collect_metadata("https://example.com")

    assert result.url == "https://example.com"
    assert result.status_code == 200
    assert "Hello World" in result.page_source
    assert len(result.cookies) == 1
    assert result.cookies[0]["name"] == "session"
    assert isinstance(result.collected_at, datetime)


@pytest.mark.asyncio
async def test_collect_metadata_no_cookies():
    """Collector should handle responses with no cookies gracefully."""
    mock_response = _build_mock_response(cookies=[])

    with patch("app.services.collector.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_response
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        result = await collect_metadata("https://example.com")

    assert result.cookies == []


# ════════════════════════ Error Cases ═══════════════════════════════════


@pytest.mark.asyncio
async def test_collect_metadata_timeout():
    """Collector should raise CollectorError on timeout."""
    with patch("app.services.collector.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.TimeoutException("timed out")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with pytest.raises(CollectorError, match="timed out"):
            await collect_metadata("https://slow-site.com")


@pytest.mark.asyncio
async def test_collect_metadata_connection_error():
    """Collector should raise CollectorError on connection failure."""
    with patch("app.services.collector.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ConnectError("refused")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with pytest.raises(CollectorError, match="Could not connect"):
            await collect_metadata("https://unreachable.com")


@pytest.mark.asyncio
async def test_collect_metadata_too_many_redirects():
    """Collector should raise CollectorError on redirect loops."""
    with patch("app.services.collector.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.TooManyRedirects(
            "Exceeded max redirects",
            request=MagicMock(),
        )
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        with pytest.raises(CollectorError, match="Too many redirects"):
            await collect_metadata("https://redirect-loop.com")
