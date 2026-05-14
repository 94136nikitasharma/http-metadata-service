"""
Background task orchestration for asynchronous metadata collection.

When the GET endpoint encounters a cache miss (URL not in the database),
it delegates the actual fetch-and-store work to this module.  The key
design constraints are:

1.  The background task runs inside the **same event loop** as FastAPI,
    using ``asyncio.create_task`` — no external worker or self-HTTP call.
2.  An in-memory set tracks URLs that are currently being fetched,
    preventing duplicate concurrent fetches for the same URL.
3.  Failures are logged but never propagated to the caller; the API
    response has already been sent by the time the task runs.
"""

import asyncio
import logging

from app.repositories.metadata_repo import MetadataRepository
from app.services.collector import CollectorError, collect_metadata

logger = logging.getLogger(__name__)

# URLs currently being fetched in the background.
# This prevents multiple concurrent tasks for the same URL.
_in_flight: set[str] = set()


def is_in_flight(url: str) -> bool:
    """Check whether a background fetch is already running for *url*."""
    return url in _in_flight


def schedule_background_collection(url: str, repo: MetadataRepository) -> None:
    """
    Schedule an asynchronous metadata collection task.

    If a fetch for the given URL is already in progress, this call is
    a no-op (deduplication).  Otherwise a new ``asyncio.Task`` is
    created on the running event loop.

    Parameters
    ----------
    url : str
        The URL whose metadata should be collected.
    repo : MetadataRepository
        Repository instance used to persist the collected data.
    """
    if url in _in_flight:
        logger.debug("Skipping duplicate background fetch for %s", url)
        return

    _in_flight.add(url)
    asyncio.create_task(_collect_and_store(url, repo))
    logger.info("Background collection scheduled for %s", url)


async def _collect_and_store(url: str, repo: MetadataRepository) -> None:
    """
    Internal coroutine that performs the actual fetch → store cycle.

    This runs independently of the request-response cycle.  On success
    the metadata is persisted and subsequent GET requests will find it.
    On failure the error is logged and the URL is removed from the
    in-flight set so it can be retried on the next request.
    """
    try:
        document = await collect_metadata(url)
        await repo.upsert(document)
        logger.info("Background collection completed for %s", url)

    except CollectorError as exc:
        logger.error(
            "Background collection failed for %s: %s", url, exc
        )

    except Exception:
        logger.exception(
            "Unexpected error during background collection for %s", url
        )

    finally:
        # Always release the in-flight lock
        _in_flight.discard(url)
