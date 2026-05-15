"""
Pydantic models for request/response validation and the
internal document structure stored in MongoDB.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


# -- Request --

class MetadataRequest(BaseModel):
    """POST request body."""
    url: HttpUrl = Field(
        ...,
        description="Fully-qualified URL to collect metadata for.",
        examples=["https://example.com"],
    )


# -- Cookie --

class CookieInfo(BaseModel):
    """Single HTTP cookie representation."""
    name: str
    value: str
    domain: str = ""
    path: str = "/"


# -- Responses --

class MetadataResponse(BaseModel):
    """Full metadata record (returned on GET 200)."""
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: list[CookieInfo] = Field(default_factory=list)
    page_source: str = ""
    status_code: int
    collected_at: datetime


class MetadataCreatedResponse(BaseModel):
    """Confirmation after POST (201)."""
    message: str = "Metadata collected and stored successfully."
    url: str
    collected_at: datetime


class MetadataAcceptedResponse(BaseModel):
    """Acknowledgement when background fetch is queued (202)."""
    message: str = (
        "Metadata not found in inventory. "
        "A background collection has been initiated. "
        "Please retry shortly."
    )
    url: str


class ErrorResponse(BaseModel):
    """Standard error envelope."""
    detail: str


# -- Internal document (not exposed via API) --

class MetadataDocument(BaseModel):
    """Represents a metadata record as stored in MongoDB."""
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: list[dict[str, Any]] = Field(default_factory=list)
    page_source: str = ""
    status_code: int = 0
    collected_at: datetime = Field(default_factory=datetime.utcnow)
