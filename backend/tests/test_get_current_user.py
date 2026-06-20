"""Tests for get_current_user FastAPI dependency.

Uses dependency_overrides to inject a controlled DB session.
"""

from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.encryption import encrypt, hmac_email
from app.core.security import create_access_token, hash_password

TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def token() -> str:
    """Create a valid JWT for testing."""
    return create_access_token(
        user_id=TEST_USER_ID,
        tenant_id=TEST_TENANT_ID,
        roles=["admin"],
    )


@pytest.fixture
def expired_token() -> str:
    """Create an expired JWT."""
    payload = {
        "sub": str(TEST_USER_ID),
        "tenant_id": str(TEST_TENANT_ID),
        "roles": ["admin"],
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    return pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


@pytest.fixture
def tampered_token(token: str) -> str:
    """Return a token with an invalid signature."""
    parts = token.split(".")
    return f"{parts[0]}.{parts[1]}.invalidsignature"


TENANT_DDL = text("""
    CREATE TABLE IF NOT EXISTS tenant (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        codigo          VARCHAR(50) NOT NULL UNIQUE,
        nombre          VARCHAR(255) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
""")

USER_DDL = text("""
    CREATE TABLE IF NOT EXISTS "user" (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email_cifrado       TEXT NOT NULL,
        email_hash          VARCHAR(64) NOT NULL,
        password_hash       VARCHAR(255) NOT NULL,
        nombre              VARCHAR(100) NOT NULL,
        apellidos           VARCHAR(255) NOT NULL,
        is_2fa_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
        totp_secret         TEXT,
        is_active           BOOLEAN NOT NULL DEFAULT TRUE,
        tenant_id           UUID NOT NULL REFERENCES tenant(id),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at          TIMESTAMPTZ
    )
""")


@pytest_asyncio.fixture
async def protected_client(app, db_session) -> AsyncGenerator[AsyncClient, None]:
    """Register test endpoint + seed DB, override get_db with db_session."""
    from fastapi import Depends
    from app.core.dependencies import get_current_user, get_db
    from app.schemas.auth import CurrentUser

    # Ensure tables and seed data
    await db_session.execute(TENANT_DDL)
    await db_session.execute(USER_DDL)
    await db_session.execute(text("DELETE FROM asignacion"))
    await db_session.execute(text('DELETE FROM "user"'))
    await db_session.execute(text("DELETE FROM tenant"))
    await db_session.execute(
        text("INSERT INTO tenant (id, codigo, nombre) VALUES (:id, :c, :c)"),
        {"id": TEST_TENANT_ID, "c": "test-tenant"},
    )
    await db_session.execute(
        text("""
            INSERT INTO "user" (id, tenant_id, email_cifrado, email_hash, password_hash, nombre, apellidos, is_active, is_2fa_enabled)
            VALUES (:uid, :tid, :ec, :eh, :ph, :n, :a, TRUE, FALSE)
        """),
        {
            "uid": TEST_USER_ID,
            "tid": TEST_TENANT_ID,
            "ec": encrypt("test@example.com"),
            "eh": hmac_email("test@example.com"),
            "ph": hash_password("TestPass123!"),
            "n": "Test",
            "a": "User",
        },
    )
    await db_session.commit()

    # Override get_db to use our session
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    @app.get("/test/me")
    async def test_me(current_user: CurrentUser = Depends(get_current_user)):
        return {
            "user_id": str(current_user.user_id),
            "tenant_id": str(current_user.tenant_id),
            "roles": current_user.roles,
        }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


class TestGetCurrentUser:
    """Tests for get_current_user FastAPI dependency."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_current_user(self, protected_client, token):
        """GET /test/me with valid token returns CurrentUser."""
        response = await protected_client.get(
            "/test/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["user_id"] == str(TEST_USER_ID)
        assert data["tenant_id"] == str(TEST_TENANT_ID)
        assert data["roles"] == ["admin"]

    @pytest.mark.asyncio
    async def test_missing_header_returns_401(self, protected_client):
        """GET /test/me without Authorization header raises 401."""
        response = await protected_client.get("/test/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, protected_client, expired_token):
        """GET /test/me with expired token raises 401."""
        response = await protected_client.get(
            "/test/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_tampered_token_returns_401(self, protected_client, tampered_token):
        """GET /test/me with invalid signature raises 401."""
        response = await protected_client.get(
            "/test/me",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_token_returns_401(self, protected_client):
        """GET /test/me with malformed token raises 401."""
        response = await protected_client.get(
            "/test/me",
            headers={"Authorization": "Bearer not.a.token"},
        )
        assert response.status_code == 401
