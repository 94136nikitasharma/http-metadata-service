"""
API route handlers for the HTTP Metadata Inventory Service.

This module defines the two core endpoints (POST and GET) and wires
together the service and repository layers.  All business logic is
delegated to dedicated modules — the routes themselves are thin
controllers responsible only for:

    1. Parsing and validating input (via Pydantic models).
    2. Invoking the appropriate service/repository call.
    3. Mapping the result to the correct HTTP response.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.database import get_database
from app.models.metadata import (
    ErrorResponse,
    MetadataAcceptedResponse,
    MetadataCreatedResponse,
    MetadataRequest,
    MetadataResponse,
)
from app.repositories.metadata_repo import MetadataRepository
from app.services.background import schedule_background_collection
from app.services.collector import CollectorError, collect_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Metadata"])


def _get_repo() -> MetadataRepository:
    """Convenience helper to obtain a repository instance."""
    return MetadataRepository(get_database())


# ────────────────────────── POST /metadata ──────────────────────────────


@router.post(
    "/metadata",
    status_code=status.HTTP_201_CREATED,
    response_model=MetadataCreatedResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or unreachable URL"},
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
    summary="Collect metadata for a URL",
    description=(
        "Accepts a URL, fetches its HTTP headers, cookies, and page "
        "source, then stores the result in the database.  Returns "
        "the stored record on success."
    ),
)
async def create_metadata(body: MetadataRequest) -> MetadataCreatedResponse:
    """
    Synchronously collect and persist metadata for the supplied URL.
    """
    url = str(body.url)
    repo = _get_repo()

    # Fetch metadata from the remote URL
    try:
        document = await collect_metadata(url)
    except CollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Persist (upsert to handle repeat submissions gracefully)
    await repo.upsert(document)

    return MetadataCreatedResponse(
        url=document.url,
        collected_at=document.collected_at,
    )


# ────────────────────────── GET /metadata ───────────────────────────────


@router.get(
    "/metadata",
    responses={
        200: {
            "model": MetadataResponse,
            "description": "Metadata found in inventory",
        },
        202: {
            "model": MetadataAcceptedResponse,
            "description": "Metadata not found — background collection started",
        },
        400: {"model": ErrorResponse, "description": "Missing or invalid URL"},
    },
    summary="Retrieve metadata for a URL",
    description=(
        "Looks up the metadata inventory for the given URL.  If a "
        "record exists, the full dataset (headers, cookies, page "
        "source) is returned immediately.  If not, a background "
        "collection task is triggered and a 202 Accepted response "
        "is returned so the client can retry later."
    ),
)
async def get_metadata(
    url: str = Query(
        ...,
        description="The URL to retrieve metadata for.",
        examples=["https://example.com"],
    ),
):
    """
    Retrieve stored metadata or trigger a background fetch.
    """
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'url' is required.",
        )

    repo = _get_repo()

    # Inventory check
    record = await repo.find_by_url(url)

    if record is not None:
        # Cache hit — return the full metadata
        return MetadataResponse(**record)

    # Cache miss — schedule background collection and acknowledge
    schedule_background_collection(url, repo)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=MetadataAcceptedResponse(url=url).model_dump(),
    )
