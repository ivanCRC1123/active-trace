"""Tests for FastAPI application startup — the app must initialise
and serve requests without crashing.
"""

import pytest


@pytest.mark.asyncio
async def test_app_creates_successfully(app):
    """``create_app()`` returns a valid FastAPI application instance."""
    assert app is not None
    assert app.title == "activia-trace"


@pytest.mark.asyncio
async def test_app_serves_request(async_client):
    """The app handles a basic request without error."""
    response = await async_client.get("/health")
    # Any valid path should respond; 404 means the app is running
    # but the path doesn't exist (which is fine — we are verifying
    # that the ASGI stack is alive).
    assert response.status_code in (200, 404)
