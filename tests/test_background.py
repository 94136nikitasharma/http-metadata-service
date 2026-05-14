"""
Unit tests for the background task orchestration module.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import background
from app.services.background import (
    _in_flight,
    is_in_flight,
    schedule_background_collection,
)


@pytest.fixture(autouse=True)
def clear_in_flight():
    """Ensure the in-flight set is empty before and after each test."""
    _in_flight.clear()
    yield
    _in_flight.clear()


def test_is_in_flight_false():
    """A URL that hasn't been scheduled should not be in-flight."""
    assert is_in_flight("https://example.com") is False


def test_is_in_flight_true():
    """A URL in the _in_flight set should be reported as in-flight."""
    _in_flight.add("https://example.com")
    assert is_in_flight("https://example.com") is True


@pytest.mark.asyncio
async def test_schedule_adds_to_in_flight():
    """Scheduling a URL should mark it as in-flight."""
    mock_repo = MagicMock()

    with patch("app.services.background.asyncio.create_task"):
        schedule_background_collection("https://example.com", mock_repo)

    assert "https://example.com" in _in_flight


@pytest.mark.asyncio
async def test_schedule_deduplicates():
    """Scheduling the same URL twice should only create one task."""
    mock_repo = MagicMock()

    with patch("app.services.background.asyncio.create_task") as mock_task:
        schedule_background_collection("https://example.com", mock_repo)
        schedule_background_collection("https://example.com", mock_repo)

    # create_task should have been called only once
    assert mock_task.call_count == 1


@pytest.mark.asyncio
async def test_collect_and_store_success():
    """
    A successful background collection should persist the document
    and remove the URL from the in-flight set.
    """
    mock_repo = AsyncMock()
    mock_document = MagicMock()

    _in_flight.add("https://example.com")

    with patch(
        "app.services.background.collect_metadata",
        new_callable=AsyncMock,
        return_value=mock_document,
    ):
        await background._collect_and_store("https://example.com", mock_repo)

    mock_repo.upsert.assert_awaited_once_with(mock_document)
    assert "https://example.com" not in _in_flight


@pytest.mark.asyncio
async def test_collect_and_store_failure_cleans_up():
    """
    A failed background collection should log the error and still
    remove the URL from the in-flight set.
    """
    mock_repo = AsyncMock()

    _in_flight.add("https://bad-url.com")

    with patch(
        "app.services.background.collect_metadata",
        new_callable=AsyncMock,
        side_effect=Exception("network error"),
    ):
        await background._collect_and_store("https://bad-url.com", mock_repo)

    # URL should be cleaned up even on failure
    assert "https://bad-url.com" not in _in_flight
    mock_repo.upsert.assert_not_awaited()
