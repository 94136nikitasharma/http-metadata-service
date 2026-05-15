"""Unit tests for the metadata collector (mocked HTTP layer)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.collector import CollectorError, collect_metadata


def _mock_response(status_code=200, headers=None, text="<html>Test</html>", cookies=None):
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = httpx.Headers(headers or {"content-type": "text/html"})
    resp.text = text

    mock_cookies = []
    for name, value in (cookies or []):
        c = MagicMock()
        c.name = name
        c.value = value
        c.domain = "example.com"
        c.path = "/"
        mock_cookies.append(c)
    resp.cookies.jar = mock_cookies

    return resp


def _patch_client(mock_response=None, side_effect=None):
    """Patch httpx.AsyncClient to return a mock or raise an error."""
    patcher = patch("app.services.collector.httpx.AsyncClient")
    MockClient = patcher.start()
    instance = AsyncMock()
    if side_effect:
        instance.get.side_effect = side_effect
    else:
        instance.get.return_value = mock_response
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    MockClient.return_value = instance
    return patcher


@pytest.mark.asyncio
async def test_collect_metadata_success():
    resp = _mock_response(
        status_code=200,
        headers={"content-type": "text/html", "server": "nginx"},
        text="<html><body>Hello World</body></html>",
        cookies=[("session", "abc123")],
    )
    patcher = _patch_client(mock_response=resp)
    try:
        result = await collect_metadata("https://example.com")
    finally:
        patcher.stop()

    assert result.url == "https://example.com"
    assert result.status_code == 200
    assert "Hello World" in result.page_source
    assert len(result.cookies) == 1
    assert result.cookies[0]["name"] == "session"
    assert isinstance(result.collected_at, datetime)


@pytest.mark.asyncio
async def test_collect_metadata_no_cookies():
    resp = _mock_response(cookies=[])
    patcher = _patch_client(mock_response=resp)
    try:
        result = await collect_metadata("https://example.com")
    finally:
        patcher.stop()
    assert result.cookies == []


@pytest.mark.asyncio
async def test_collect_metadata_timeout():
    patcher = _patch_client(side_effect=httpx.TimeoutException("timed out"))
    try:
        with pytest.raises(CollectorError, match="timed out"):
            await collect_metadata("https://slow-site.com")
    finally:
        patcher.stop()


@pytest.mark.asyncio
async def test_collect_metadata_connection_error():
    patcher = _patch_client(side_effect=httpx.ConnectError("refused"))
    try:
        with pytest.raises(CollectorError, match="Could not connect"):
            await collect_metadata("https://unreachable.com")
    finally:
        patcher.stop()


@pytest.mark.asyncio
async def test_collect_metadata_too_many_redirects():
    patcher = _patch_client(
        side_effect=httpx.TooManyRedirects("Exceeded max redirects", request=MagicMock())
    )
    try:
        with pytest.raises(CollectorError, match="Too many redirects"):
            await collect_metadata("https://redirect-loop.com")
    finally:
        patcher.stop()
