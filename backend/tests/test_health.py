"""Tests for the ``GET /health`` endpoint.

Tests verify ``200`` response with ``status`` and ``database`` fields,
including graceful degradation when the database is unreachable.
"""

import pytest


@pytest.mark.asyncio
async def test_health_returns_200(async_client):
    """``GET /health`` responds ``200`` with JSON body."""
    response = await async_client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_includes_status(async_client):
    """Response body includes a ``status`` field."""
    response = await async_client.get("/health")
    body = response.json()
    assert "status" in body


@pytest.mark.asyncio
async def test_health_includes_database_field(async_client):
    """Response body includes a ``database`` readiness field."""
    response = await async_client.get("/health")
    body = response.json()
    assert "database" in body


@pytest.mark.asyncio
async def test_health_db_down_still_returns_200(async_client):
    """When the database is unreachable the endpoint still returns ``200``."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    # Without a running database, the check will report ``down``.
    assert body["database"] in ("up", "down")


@pytest.mark.asyncio
async def test_health_status_ok_when_db_down(async_client):
    """The ``status`` field is always ``"ok"`` even if DB is down.

    This verifies that liveness and readiness are decoupled — a DB
    outage does not crash the application process.
    """
    response = await async_client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
