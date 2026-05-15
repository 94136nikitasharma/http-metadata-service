"""Unit tests for the background task module."""

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
    """Reset in-flight set between tests."""
    _in_flight.clear()
    yield
    _in_flight.clear()


def test_is_in_flight_false():
    assert is_in_flight("https://example.com") is False


def test_is_in_flight_true():
    _in_flight.add("https://example.com")
    assert is_in_flight("https://example.com") is True


@pytest.mark.asyncio
async def test_schedule_adds_to_in_flight():
    mock_repo = MagicMock()
    with patch("app.services.background.asyncio.create_task"):
        schedule_background_collection("https://example.com", mock_repo)
    assert "https://example.com" in _in_flight


@pytest.mark.asyncio
async def test_schedule_deduplicates():
    """Same URL scheduled twice should only create one task."""
    mock_repo = MagicMock()
    with patch("app.services.background.asyncio.create_task") as mock_task:
        schedule_background_collection("https://example.com", mock_repo)
        schedule_background_collection("https://example.com", mock_repo)
    assert mock_task.call_count == 1


@pytest.mark.asyncio
async def test_collect_and_store_success():
    mock_repo = AsyncMock()
    mock_doc = MagicMock()
    _in_flight.add("https://example.com")

    with patch("app.services.background.collect_metadata", new_callable=AsyncMock, return_value=mock_doc):
        await background._collect_and_store("https://example.com", mock_repo)

    mock_repo.upsert.assert_awaited_once_with(mock_doc)
    assert "https://example.com" not in _in_flight  # cleaned up


@pytest.mark.asyncio
async def test_collect_and_store_failure_cleans_up():
    """On failure, URL should still be removed from in-flight set."""
    mock_repo = AsyncMock()
    _in_flight.add("https://bad-url.com")

    with patch("app.services.background.collect_metadata", new_callable=AsyncMock, side_effect=Exception("boom")):
        await background._collect_and_store("https://bad-url.com", mock_repo)

    assert "https://bad-url.com" not in _in_flight
    mock_repo.upsert.assert_not_awaited()
