"""
Pydantic models for the HTTP Metadata Inventory Service.

These models define the data contracts for API requests, responses,
and the internal document structure stored in MongoDB.  Using Pydantic
ensures automatic validation, serialisation, and clear documentation
via FastAPI's OpenAPI schema.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


# ──────────────────────────── Request Models ────────────────────────────


class MetadataRequest(BaseModel):
    """Incoming request body for the POST endpoint."""

    url: HttpUrl = Field(
        ...,
        description="The fully-qualified URL to collect metadata for.",
        examples=["https://example.com"],
    )


# ──────────────────────────── Cookie Schema ─────────────────────────────


class CookieInfo(BaseModel):
    """Structured representation of a single HTTP cookie."""

    name: str
    value: str
    domain: str = ""
    path: str = "/"


# ──────────────────────────── Response Models ───────────────────────────


class MetadataResponse(BaseModel):
    """Full metadata record returned by the GET endpoint (200 OK)."""

    url: str = Field(..., description="The original URL that was fetched.")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="HTTP response headers received from the URL.",
    )
    cookies: list[CookieInfo] = Field(
        default_factory=list,
        description="Cookies set by the remote server.",
    )
    page_source: str = Field(
        "",
        description="Raw HTML page source returned by the server.",
    )
    status_code: int = Field(
        ...,
        description="HTTP status code received from the remote server.",
    )
    collected_at: datetime = Field(
        ...,
        description="UTC timestamp of when the metadata was collected.",
    )


class MetadataCreatedResponse(BaseModel):
    """Confirmation returned after a successful POST (201 Created)."""

    message: str = "Metadata collected and stored successfully."
    url: str
    collected_at: datetime


class MetadataAcceptedResponse(BaseModel):
    """Acknowledgement returned when a background fetch is queued (202 Accepted)."""

    message: str = (
        "Metadata not found in inventory. "
        "A background collection has been initiated. "
        "Please retry shortly."
    )
    url: str


class ErrorResponse(BaseModel):
    """Standard error envelope for client-facing error messages."""

    detail: str


# ───────────────────────── Internal Document ────────────────────────────


class MetadataDocument(BaseModel):
    """
    Internal representation of a metadata document as stored in MongoDB.

    This model is never exposed directly to the API consumer; it is used
    by the repository layer for serialisation/deserialisation.
    """

    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: list[dict[str, Any]] = Field(default_factory=list)
    page_source: str = ""
    status_code: int = 0
    collected_at: datetime = Field(default_factory=datetime.utcnow)
