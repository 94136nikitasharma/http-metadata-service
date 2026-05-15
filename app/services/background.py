"""
Background worker for async metadata collection.

When GET hits a cache miss, this module schedules a fetch-and-store
task on the event loop. Key points:
- Uses asyncio.create_task (no external worker, no self-HTTP calls)
- Tracks in-flight URLs to avoid duplicate fetches
- Errors are logged, never propagated (response is already sent)
"""

import asyncio
import logging

from app.repositories.metadata_repo import MetadataRepository
from app.services.collector import CollectorError, collect_metadata

logger = logging.getLogger(__name__)

# Tracks URLs currently being fetched — prevents duplicates
_in_flight: set[str] = set()


def get_pending_count() -> int:
    """How many background fetches are currently running."""
    return len(_in_flight)


def is_in_flight(url: str) -> bool:
    """Check if a background fetch is already running for this URL."""
    return url in _in_flight


def schedule_background_collection(url: str, repo: MetadataRepository) -> None:
    """
    Kick off an async metadata collection task.
    If the same URL is already being fetched, this is a no-op.
    """
    if url in _in_flight:
        logger.debug("Skipping duplicate background fetch for %s", url)
        return

    _in_flight.add(url)
    task = asyncio.create_task(
        _collect_and_store(url, repo),
        name=f"bg-collect-{url}",
    )
    logger.info("Background collection scheduled for %s", url)


async def _collect_and_store(url: str, repo: MetadataRepository) -> None:
    """
    Actually fetch the URL and persist the result.
    Runs independently of the request-response cycle.
    """
    try:
        document = await collect_metadata(url)
        await repo.upsert(document)
        logger.info("Background collection completed for %s", url)

    except CollectorError as exc:
        logger.error("Background collection failed for %s: %s", url, exc)

    except Exception:
        logger.exception("Unexpected error collecting %s", url)

    finally:
        _in_flight.discard(url)
