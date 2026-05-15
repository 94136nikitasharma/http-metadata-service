"""
API route handlers — thin controllers that wire together
the service and repository layers.
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
    return MetadataRepository(get_database())


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
        "source, then stores the result in the database."
    ),
)
async def create_metadata(body: MetadataRequest) -> MetadataCreatedResponse:
    """Synchronously collect and persist metadata for the given URL."""
    url = str(body.url)
    repo = _get_repo()

    try:
        document = await collect_metadata(url)
    except CollectorError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # upsert handles repeat submissions gracefully
    await repo.upsert(document)

    return MetadataCreatedResponse(
        url=document.url,
        collected_at=document.collected_at,
    )


@router.get(
    "/metadata",
    responses={
        200: {"model": MetadataResponse, "description": "Metadata found"},
        202: {"model": MetadataAcceptedResponse, "description": "Background collection started"},
        400: {"model": ErrorResponse, "description": "Missing or invalid URL"},
    },
    summary="Retrieve metadata for a URL",
    description=(
        "Looks up stored metadata for the given URL. Returns it "
        "immediately if found, otherwise triggers a background "
        "collection and returns 202 Accepted."
    ),
)
async def get_metadata(
    url: str = Query(
        ...,
        description="The URL to look up.",
        examples=["https://example.com"],
    ),
):
    """Retrieve stored metadata or trigger a background fetch."""
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'url' is required.",
        )

    repo = _get_repo()
    record = await repo.find_by_url(url)

    if record is not None:
        return MetadataResponse(**record)

    # Not in DB yet — kick off background collection
    schedule_background_collection(url, repo)

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=MetadataAcceptedResponse(url=url).model_dump(),
    )
