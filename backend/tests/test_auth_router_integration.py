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


def _login_payload() -> dict:
    return {"tenant_code": TENANT_CODE, "email": ADMIN_EMAIL, "password": ADMIN_PASS}


class TestLoginIntegration:
    """POST /api/auth/login via real HTTP."""

    async def test_login_success_access_token_in_body(
        self, async_client: AsyncClient, seeded_db
    ):
        """Access token is in JSON body; refresh token must NOT be in body."""
        resp = await async_client.post("/api/auth/login", json=_login_payload())
        assert resp.status_code == 200, f"body={resp.text}"
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" not in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    async def test_login_sets_httponly_cookie(
        self, async_client: AsyncClient, seeded_db
    ):
        """Login sets a refresh_token httpOnly cookie."""
        resp = await async_client.post("/api/auth/login", json=_login_payload())
        assert resp.status_code == 200
        # httpx stores cookies; verify the Set-Cookie header is present
        set_cookie = resp.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie.lower() or "samesite=strict" in set_cookie.lower()

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
    """POST /api/auth/refresh via real HTTP (cookie-based)."""

    async def _login(self, async_client: AsyncClient) -> str:
        """Login and return the access_token.  The refresh cookie is stored in the client jar."""
        resp = await async_client.post("/api/auth/login", json=_login_payload())
        assert resp.status_code == 200
        return resp.json()["access_token"]

    async def test_refresh_success_cookie(self, async_client: AsyncClient, seeded_db):
        """Refresh reads cookie from jar, returns new access_token, rotates cookie."""
        await self._login(async_client)
        # Capture original cookie value before rotating
        original_cookie = async_client.cookies.get("refresh_token")
        assert original_cookie is not None

        resp = await async_client.post("/api/auth/refresh")
        assert resp.status_code == 200, f"body={resp.text}"
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" not in body  # token is in cookie, not in body

        # New cookie value must differ (rotation)
        new_cookie = async_client.cookies.get("refresh_token")
        assert new_cookie is not None
        assert new_cookie != original_cookie

    async def test_refresh_rotates_revokes_old_token(
        self, async_client: AsyncClient, seeded_db
    ):
        """After rotation, the original token is revoked."""
        await self._login(async_client)
        original_cookie = async_client.cookies.get("refresh_token")

        # First refresh — rotates the token
        resp = await async_client.post("/api/auth/refresh")
        assert resp.status_code == 200

        # Restore the original (now revoked) cookie and try again
        async_client.cookies.set("refresh_token", original_cookie)
        resp2 = await async_client.post("/api/auth/refresh")
        assert resp2.status_code == 401

    async def test_refresh_no_cookie_returns_401(
        self, async_client: AsyncClient, seeded_db
    ):
        """Refresh without a cookie (no prior login) returns 401."""
        # Fresh client — no cookie in jar
        resp = await async_client.post("/api/auth/refresh")
        assert resp.status_code == 401

    async def test_refresh_bad_cookie_value_returns_401(
        self, async_client: AsyncClient, seeded_db
    ):
        """Refresh with a cookie set to a random invalid value returns 401."""
        async_client.cookies.set("refresh_token", "this_is_not_a_valid_token")
        resp = await async_client.post("/api/auth/refresh")
        assert resp.status_code == 401


class TestLogoutIntegration:
    """POST /api/auth/logout via real HTTP (cookie-based)."""

    async def _login(self, async_client: AsyncClient) -> str:
        resp = await async_client.post("/api/auth/login", json=_login_payload())
        assert resp.status_code == 200
        return resp.json()["access_token"]

    async def test_logout_revokes_and_clears_cookie(
        self, async_client: AsyncClient, seeded_db
    ):
        """Logout revokes the server-side token and clears the cookie."""
        access_token = await self._login(async_client)
        assert async_client.cookies.get("refresh_token") is not None

        resp = await async_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200, f"body={resp.text}"
        assert resp.json()["detail"] == "Logged out successfully."

        # Cookie should be expired/cleared in the response
        set_cookie = resp.headers.get("set-cookie", "")
        assert "refresh_token" in set_cookie
        # Starlette sets max-age=0 on delete_cookie
        assert "max-age=0" in set_cookie.lower() or "max-age=0" in set_cookie

    async def test_logout_without_cookie_still_succeeds(
        self, async_client: AsyncClient, seeded_db
    ):
        """Logout is idempotent — no cookie present is not an error."""
        access_token = await self._login(async_client)
        # Remove cookie from client jar
        async_client.cookies.delete("refresh_token")

        resp = await async_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200

    async def test_logout_revokes_refresh_server_side(
        self, async_client: AsyncClient, seeded_db
    ):
        """After logout, the refresh token is invalidated server-side (/refresh → 401)."""
        access_token = await self._login(async_client)
        # Capture the refresh cookie before logout
        saved_cookie = async_client.cookies.get("refresh_token")
        assert saved_cookie is not None

        await async_client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # Restore the revoked cookie and attempt refresh → must be 401
        async_client.cookies.set("refresh_token", saved_cookie)
        resp = await async_client.post("/api/auth/refresh")
        assert resp.status_code == 401

    async def test_logout_unauthenticated(self, async_client: AsyncClient, seeded_db):
        """Logout without a valid access token returns 401."""
        resp = await async_client.post("/api/auth/logout")
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


class TestMePermissionsIntegration:
    """GET /api/auth/me/permissions via real HTTP."""

    async def _login(self, async_client: AsyncClient) -> str:
        resp = await async_client.post("/api/auth/login", json=_login_payload())
        assert resp.status_code == 200
        return resp.json()["access_token"]

    async def test_unauthenticated_returns_401(
        self, async_client: AsyncClient, seeded_db
    ):
        """No access token → 401."""
        resp = await async_client.get("/api/auth/me/permissions")
        assert resp.status_code == 401

    async def test_no_roles_returns_empty_permissions(
        self, async_client: AsyncClient, seeded_db
    ):
        """User with no role assignments → empty permissions dict."""
        access_token = await self._login(async_client)
        resp = await async_client.get(
            "/api/auth/me/permissions",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200, f"body={resp.text}"
        body = resp.json()
        assert "permissions" in body
        assert body["permissions"] == {}

    async def test_with_role_returns_permissions(
        self, async_client: AsyncClient, seeded_db, db_session
    ):
        """User with an assigned role → permissions dict has its entries."""
        from app.models.permiso import Permiso
        from app.models.rol import Rol
        from app.models.rol_permiso import RolPermiso
        from app.models.user_rol import UserRol

        tenant, user = seeded_db

        # Seed: Permiso → Rol → RolPermiso → UserRol
        permiso = Permiso(
            tenant_id=tenant.id,
            codigo="calificaciones:importar",
            modulo="calificaciones",
        )
        db_session.add(permiso)
        await db_session.flush()
        await db_session.refresh(permiso)

        rol = Rol(tenant_id=tenant.id, nombre="ADMIN_TEST")
        db_session.add(rol)
        await db_session.flush()
        await db_session.refresh(rol)

        rol_permiso = RolPermiso(
            tenant_id=tenant.id,
            rol_id=rol.id,
            permiso_id=permiso.id,
            scope="all",
        )
        db_session.add(rol_permiso)

        user_rol = UserRol(
            tenant_id=tenant.id,
            user_id=user.id,
            rol_id=rol.id,
        )
        db_session.add(user_rol)
        await db_session.commit()

        access_token = await self._login(async_client)
        resp = await async_client.get(
            "/api/auth/me/permissions",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200, f"body={resp.text}"
        perms = resp.json()["permissions"]
        assert "calificaciones:importar" in perms
        assert perms["calificaciones:importar"] == "all"

    async def test_multi_role_union_and_scope_precedence(
        self, async_client: AsyncClient, seeded_db, db_session
    ):
        """Union across roles: if same permission appears with 'own' and 'all',
        the effective scope must be 'all'. A permission exclusive to one role
        must also appear in the union.

        Setup:
          ROL_A  → calificaciones:importar (own), comunicaciones:enviar (own)
          ROL_B  → calificaciones:importar (all)          ← conflict: all wins
        User holds both ROL_A and ROL_B.
        Expected: calificaciones:importar → all, comunicaciones:enviar → own
        """
        from app.models.permiso import Permiso
        from app.models.rol import Rol
        from app.models.rol_permiso import RolPermiso
        from app.models.user_rol import UserRol

        tenant, user = seeded_db

        # Permisos
        perm_calc = Permiso(
            tenant_id=tenant.id, codigo="calificaciones:importar", modulo="calificaciones"
        )
        perm_com = Permiso(
            tenant_id=tenant.id, codigo="comunicaciones:enviar", modulo="comunicaciones"
        )
        db_session.add_all([perm_calc, perm_com])
        await db_session.flush()
        await db_session.refresh(perm_calc)
        await db_session.refresh(perm_com)

        # Roles
        rol_a = Rol(tenant_id=tenant.id, nombre="ROL_A")
        rol_b = Rol(tenant_id=tenant.id, nombre="ROL_B")
        db_session.add_all([rol_a, rol_b])
        await db_session.flush()
        await db_session.refresh(rol_a)
        await db_session.refresh(rol_b)

        # ROL_A: calificaciones:importar(own) + comunicaciones:enviar(own)
        # ROL_B: calificaciones:importar(all)
        db_session.add_all([
            RolPermiso(tenant_id=tenant.id, rol_id=rol_a.id, permiso_id=perm_calc.id, scope="own"),
            RolPermiso(tenant_id=tenant.id, rol_id=rol_a.id, permiso_id=perm_com.id, scope="own"),
            RolPermiso(tenant_id=tenant.id, rol_id=rol_b.id, permiso_id=perm_calc.id, scope="all"),
        ])

        # User holds both roles
        db_session.add_all([
            UserRol(tenant_id=tenant.id, user_id=user.id, rol_id=rol_a.id),
            UserRol(tenant_id=tenant.id, user_id=user.id, rol_id=rol_b.id),
        ])
        await db_session.commit()

        access_token = await self._login(async_client)
        resp = await async_client.get(
            "/api/auth/me/permissions",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 200, f"body={resp.text}"
        perms = resp.json()["permissions"]

        # Both permissions appear (union)
        assert "calificaciones:importar" in perms
        assert "comunicaciones:enviar" in perms

        # Scope precedence: 'all' wins over 'own' for the conflicting permission
        assert perms["calificaciones:importar"] == "all"

        # Permission exclusive to ROL_A retains its scope
        assert perms["comunicaciones:enviar"] == "own"


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
