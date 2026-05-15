"""
HTTP metadata collector — makes outbound requests and extracts
headers, cookies, and page source from target URLs.

Decoupled from the DB layer so it's easy to test in isolation.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models.metadata import MetadataDocument

logger = logging.getLogger(__name__)


class CollectorError(Exception):
    """Raised when metadata collection fails (timeout, DNS, etc.)."""


async def collect_metadata(url: str) -> MetadataDocument:
    """Fetch the target URL and return structured metadata."""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout),
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            response = await client.get(url)

        cookies = [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
            }
            for cookie in response.cookies.jar
        ]

        document = MetadataDocument(
            url=url,
            headers=dict(response.headers),
            cookies=cookies,
            page_source=response.text,
            status_code=response.status_code,
            collected_at=datetime.now(timezone.utc),
        )

        logger.info(
            "Collected metadata for %s (status %d, %d bytes)",
            url, response.status_code, len(response.text),
        )
        return document

    except httpx.TimeoutException as exc:
        logger.warning("Timeout fetching %s: %s", url, exc)
        raise CollectorError(f"Request timed out for URL: {url}") from exc

    except httpx.ConnectError as exc:
        logger.warning("Connection error for %s: %s", url, exc)
        raise CollectorError(f"Could not connect to URL: {url}") from exc

    except httpx.TooManyRedirects as exc:
        logger.warning("Too many redirects for %s: %s", url, exc)
        raise CollectorError(f"Too many redirects for URL: {url}") from exc

    except httpx.HTTPError as exc:
        logger.error("HTTP error fetching %s: %s", url, exc)
        raise CollectorError(f"HTTP error for URL: {url} — {exc}") from exc
