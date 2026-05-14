"""
HTTP metadata collector service.

Responsible for making outbound HTTP requests to target URLs and
extracting structured metadata (headers, cookies, page source).
This module is intentionally decoupled from the database layer
so it can be tested and reused independently.
"""

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models.metadata import MetadataDocument

logger = logging.getLogger(__name__)


class CollectorError(Exception):
    """Raised when metadata collection fails for a recoverable reason."""


async def collect_metadata(url: str) -> MetadataDocument:
    """
    Fetch the target URL and return a structured metadata document.

    Parameters
    ----------
    url : str
        The fully-qualified URL to fetch.

    Returns
    -------
    MetadataDocument
        Parsed metadata ready for persistence.

    Raises
    ------
    CollectorError
        If the HTTP request fails (timeout, DNS, connection refused, etc.).
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout),
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            response = await client.get(url)

        # Extract cookies into a serialisable list of dicts
        cookies = [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
            }
            for cookie in response.cookies.jar
        ]

        # Build the document
        document = MetadataDocument(
            url=url,
            headers=dict(response.headers),
            cookies=cookies,
            page_source=response.text,
            status_code=response.status_code,
            collected_at=datetime.now(timezone.utc),
        )

        logger.info(
            "Collected metadata for %s — status %d, %d bytes",
            url,
            response.status_code,
            len(response.text),
        )
        return document

    except httpx.TimeoutException as exc:
        logger.warning("Timeout while fetching %s: %s", url, exc)
        raise CollectorError(f"Request timed out for URL: {url}") from exc

    except httpx.ConnectError as exc:
        logger.warning("Connection error for %s: %s", url, exc)
        raise CollectorError(
            f"Could not connect to URL: {url}"
        ) from exc

    except httpx.TooManyRedirects as exc:
        logger.warning("Too many redirects for %s: %s", url, exc)
        raise CollectorError(
            f"Too many redirects for URL: {url}"
        ) from exc

    except httpx.HTTPError as exc:
        logger.error("HTTP error while fetching %s: %s", url, exc)
        raise CollectorError(
            f"HTTP error while fetching URL: {url} — {exc}"
        ) from exc
