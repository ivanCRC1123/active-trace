"""Integration tests for the auth router endpoints.

Tests the full HTTP request → router → service → repository → DB
stack using the test DB (via conftest's session-scoped engine init).
Each test seeds its own tenant + user data directly.
"""

from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password

TENANT_CODE = "tupad"
ADMIN_EMAIL = "admin@tupad.edu.ar"
ADMIN_PASS = "Admin123!"


@pytest_asyncio.fixture
async def seeded_db(db_session):
    """Seed tenant + admin user + clean tokens. Returns (tenant, user)."""
    from app.models.tenant import Tenant
    from app.models.user import User
    from sqlalchemy import select, text

    # Clean slate — asignacion first (RESTRICT FK on user would block otherwise)
    await db_session.execute(text("DELETE FROM asignacion"))
    await db_session.execute(text("DELETE FROM refresh_token"))
    await db_session.execute(text("DELETE FROM recovery_token"))
    await db_session.execute(text('DELETE FROM "user"'))
    await db_session.execute(text("DELETE FROM tenant"))
    await db_session.commit()

    # Create tenant
    tenant = Tenant(codigo=TENANT_CODE, nombre="TUPAD")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)

    # Create user
    user = User(
        email_cifrado=encrypt(ADMIN_EMAIL),
        email_hash=hmac_email(ADMIN_EMAIL),
        password_hash=hash_password(ADMIN_PASS),
        nombre="Admin",
        apellidos="Sistema",
        is_active=True,
        is_2fa_enabled=False,
        tenant_id=tenant.id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    await db_session.commit()
    return tenant, user


class TestLoginIntegration:
    """POST /api/auth/login via real HTTP."""

    async def test_login_success(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
        })
        assert resp.status_code == 200, f"body={resp.text}"
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    async def test_login_wrong_password(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": "WrongPass123!",
        })
        assert resp.status_code == 401

    async def test_login_unknown_tenant(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": "nonexistent",
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
        })
        assert resp.status_code == 401

    async def test_login_unknown_user(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": "unknown@test.com",
            "password": ADMIN_PASS,
        })
        assert resp.status_code == 401


class TestRefreshIntegration:
    """POST /api/auth/refresh via real HTTP."""

    async def _login(self, async_client):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
        })
        assert resp.status_code == 200
        return resp.json()

    async def test_refresh_success(self, async_client: AsyncClient, seeded_db):
        tokens = await self._login(async_client)
        refresh_token = tokens["refresh_token"]

        resp = await async_client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200, f"body={resp.text}"
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

        # Old token should be revoked
        resp2 = await async_client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp2.status_code == 401

    async def test_refresh_invalid(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/refresh", json={
            "refresh_token": "invalid_token",
        })
        assert resp.status_code == 401


class TestLogoutIntegration:
    """POST /api/auth/logout via real HTTP."""

    async def _login(self, async_client):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
        })
        assert resp.status_code == 200
        return resp.json()

    async def test_logout_with_token(self, async_client: AsyncClient, seeded_db):
        tokens = await self._login(async_client)
        resp = await async_client.post("/api/auth/logout", json={
            "refresh_token": tokens["refresh_token"],
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 200, f"body={resp.text}"
        assert resp.json()["detail"] == "Logged out successfully."

    async def test_logout_without_body_token(self, async_client: AsyncClient, seeded_db):
        tokens = await self._login(async_client)
        resp = await async_client.post("/api/auth/logout", json={}, headers={
            "Authorization": f"Bearer {tokens['access_token']}",
        })
        assert resp.status_code == 200

    async def test_logout_unauthenticated(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/logout", json={
            "refresh_token": "some_token",
        })
        # HTTPBearer(auto_error=True) returns 401, not 403
        assert resp.status_code == 401


class TestForgotResetIntegration:
    """POST /api/auth/forgot and /reset via real HTTP."""

    async def test_forgot_creates_token(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/forgot", json={
            "email": ADMIN_EMAIL,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["recovery_token"] is not None

    async def test_forgot_unknown_email(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/forgot", json={
            "email": "unknown@test.com",
        })
        assert resp.status_code == 200
        assert resp.json()["recovery_token"] is None

    async def test_reset_password(self, async_client: AsyncClient, seeded_db):
        forgot_resp = await async_client.post("/api/auth/forgot", json={
            "email": ADMIN_EMAIL,
        })
        recovery_token = forgot_resp.json()["recovery_token"]

        new_pass = "NewPass789!"
        resp = await async_client.post("/api/auth/reset", json={
            "token": recovery_token,
            "new_password": new_pass,
        })
        assert resp.status_code == 200

        # Login with new password works
        login1 = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": new_pass,
        })
        assert login1.status_code == 200

        # Old password fails
        login2 = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
        })
        assert login2.status_code == 401

    async def test_reset_used_token(self, async_client: AsyncClient, seeded_db):
        forgot_resp = await async_client.post("/api/auth/forgot", json={
            "email": ADMIN_EMAIL,
        })
        token = forgot_resp.json()["recovery_token"]
        await async_client.post("/api/auth/reset", json={
            "token": token, "new_password": "NewPass789!",
        })
        resp = await async_client.post("/api/auth/reset", json={
            "token": token, "new_password": "AnotherPass1!",
        })
        assert resp.status_code == 401


class TestTwoFAIntegration:
    """2FA flow via real HTTP."""

    async def _login(self, async_client):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
        })
        assert resp.status_code == 200
        return resp.json()

    async def test_enroll_requires_auth(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/2fa/enroll")
        # HTTPBearer(auto_error=True) returns 401, not 403
        assert resp.status_code == 401

    async def test_enroll_and_verify(self, async_client: AsyncClient, seeded_db):
        tokens = await self._login(async_client)

        # Enroll
        enroll = await async_client.post("/api/auth/2fa/enroll", headers={
            "Authorization": f"Bearer {tokens['access_token']}",
        })
        assert enroll.status_code == 200
        secret = enroll.json()["secret"]

        # Verify with real TOTP code
        import pyotp
        code = pyotp.TOTP(secret).now()
        verify = await async_client.post("/api/auth/2fa/verify", json={"code": code}, headers={
            "Authorization": f"Bearer {tokens['access_token']}",
        })
        assert verify.status_code == 200

        # Login now requires 2FA
        login2 = await self._login(async_client)
        assert login2.get("requires_2fa") is True
        session_token = login2["session_token"]

        # Complete 2FA
        final = await async_client.post("/api/auth/2fa/verify-login", json={
            "session_token": session_token,
            "code": code,
        })
        assert final.status_code == 200
        assert "access_token" in final.json()


class TestProtectedIntegration:
    """get_current_user via protected endpoints."""

    async def test_valid_token(self, async_client: AsyncClient, seeded_db):
        resp = await async_client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE,
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS,
        })
        access_token = resp.json()["access_token"]

        resp2 = await async_client.post("/api/auth/logout", json={}, headers={
            "Authorization": f"Bearer {access_token}",
        })
        assert resp2.status_code == 200

    async def test_expired_token(self, async_client: AsyncClient, seeded_db):
        from datetime import datetime, timedelta, timezone
        import jwt as pyjwt
        from app.core.config import settings

        payload = {
            "sub": "00000000-0000-0000-0000-000000000001",
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "roles": [],
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired = pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

        resp = await async_client.post("/api/auth/logout", json={}, headers={
            "Authorization": f"Bearer {expired}",
        })
        assert resp.status_code == 401
