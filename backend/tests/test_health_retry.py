"""Tests for MongoDB retry logic and DB-aware /health endpoint."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from oslo_config import cfg

from backend import main
from backend.config import get_settings
from backend.database import state as db_state
from rca_copilot import mongo_utils
from rca_copilot.config import register_opts


class ConnectionFailure(Exception):
    """Stand-in for pymongo.errors.ConnectionFailure."""


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# connect_with_retry tests
# ---------------------------------------------------------------------------


def test_connect_with_retry_succeeds_first_try():
    """If ping succeeds immediately, connect_with_retry returns the client."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})

    with patch("rca_copilot.mongo_utils.create_mongo_client", return_value=mock_client):
        result = _run(mongo_utils.connect_with_retry("mongodb://test"))
    assert result is mock_client
    mock_client.close.assert_not_called()


def test_connect_with_retry_succeeds_after_failures():
    """If ping fails a few times then succeeds, retry eventually connects."""
    mock_client = MagicMock()
    call_count = 0

    async def fake_ping(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionFailure("transient")
        return {"ok": 1}

    mock_client.admin.command = fake_ping

    with patch("rca_copilot.mongo_utils.create_mongo_client", return_value=mock_client), \
         patch("rca_copilot.mongo_utils.asyncio.sleep", new=AsyncMock()):
        result = _run(mongo_utils.connect_with_retry("mongodb://test"))
    assert result is mock_client
    assert call_count == 3


def test_connect_with_retry_exhausts_and_raises():
    """If ping fails for all attempts, the client is closed and the error propagates."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=ConnectionFailure("unreachable"))

    original_retries = mongo_utils.MONGO_CONNECT_MAX_RETRIES
    mongo_utils.MONGO_CONNECT_MAX_RETRIES = 2
    try:
        with patch("rca_copilot.mongo_utils.create_mongo_client", return_value=mock_client), \
             patch("rca_copilot.mongo_utils.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(ConnectionFailure):
                _run(mongo_utils.connect_with_retry("mongodb://test"))
        mock_client.close.assert_called_once()
    finally:
        mongo_utils.MONGO_CONNECT_MAX_RETRIES = original_retries


# ---------------------------------------------------------------------------
# DB-aware /health endpoint tests
# ---------------------------------------------------------------------------


def test_health_returns_503_when_db_not_ready():
    """When db_state.db_ready is False, /health returns 503."""
    app = main.create_app(lifespan_context=None)
    db_state.db_ready = False
    db_state.client = None

    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/health")

    try:
        response = _run(_request())
        assert response.status_code == 503
        assert "unavailable" in response.json()["status"]
    finally:
        db_state.db_ready = False
        db_state.client = None


def test_health_returns_503_when_ping_fails():
    """When the client exists but ping fails, /health returns 503."""
    app = main.create_app(lifespan_context=None)
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=Exception("ping failed"))
    db_state.db_ready = True
    db_state.client = mock_client

    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/health")

    try:
        response = _run(_request())
        assert response.status_code == 503
        assert "MongoDB ping failed" in response.json()["reason"]
    finally:
        db_state.db_ready = False
        db_state.client = None


def test_health_returns_200_when_db_healthy():
    """When db_state is ready and ping succeeds, /health returns 200."""
    app = main.create_app(lifespan_context=None)
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})
    db_state.db_ready = True
    db_state.client = mock_client

    async def _request():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/health")

    try:
        response = _run(_request())
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        db_state.db_ready = False
        db_state.client = None
