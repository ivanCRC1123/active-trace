"""Tests for C-04 RBAC: permission resolution and require_permission guard.

Covers:
- get_user_permissions() — effective permission union across roles
- check_permission()     — single-permission check with scope
- require_permission()   — FastAPI dependency guard (via /me endpoint)
- JWT roles claim        — populated from UserRol at login and refresh
"""

from datetime import datetime, timezone

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import check_permission, get_user_permissions
from app.core.security import hash_password

TENANT_CODE = "rbac-test"
USER_PASS = "Admin123!"
ADMIN_EMAIL = "rbac.admin@tupad.edu.ar"
PROFESOR_EMAIL = "rbac.profesor@tupad.edu.ar"
ALUMNO_EMAIL = "rbac.alumno@tupad.edu.ar"


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def rbac_db(db_session: AsyncSession) -> dict:
    """
    Seed a minimal RBAC environment in trace_test and commit it.

    Environment:
      tenant  : rbac-test
      users   : admin (→ ADMIN role), profesor (→ PROFESOR role), alumno (no role)
      roles   : ADMIN, PROFESOR
      permisos: comunicacion:confirmar_aviso, calificaciones:importar, auditoria:ver
      matrix  : ADMIN  → confirmar(all) / importar(all) / auditoria(all)
                PROFESOR → confirmar(all) / importar(own)

    Returns plain UUID values captured before commit so they remain usable
    after expire_on_commit.
    """
    from app.models.permiso import Permiso
    from app.models.rol import Rol
    from app.models.rol_permiso import RolPermiso
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.user_rol import UserRol

    # Clean slate — delete in FK dependency order
    await db_session.execute(text("DELETE FROM user_rol"))
    await db_session.execute(text("DELETE FROM rol_permiso"))
    await db_session.execute(text("DELETE FROM permiso"))
    await db_session.execute(text("DELETE FROM rol"))
    await db_session.execute(text("DELETE FROM refresh_token"))
    await db_session.execute(text("DELETE FROM recovery_token"))
    await db_session.execute(text('DELETE FROM "user"'))
    await db_session.execute(text("DELETE FROM tenant"))
    await db_session.commit()

    # Tenant
    tenant = Tenant(codigo=TENANT_CODE, nombre="RBAC Test Tenant")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    tid = tenant.id

    # Users
    admin_user = User(
        email=ADMIN_EMAIL, password_hash=hash_password(USER_PASS),
        nombre="Admin", apellido="Test",
        is_active=True, is_2fa_enabled=False, tenant_id=tid,
    )
    profesor_user = User(
        email=PROFESOR_EMAIL, password_hash=hash_password(USER_PASS),
        nombre="Profesor", apellido="Test",
        is_active=True, is_2fa_enabled=False, tenant_id=tid,
    )
    alumno_user = User(
        email=ALUMNO_EMAIL, password_hash=hash_password(USER_PASS),
        nombre="Alumno", apellido="Test",
        is_active=True, is_2fa_enabled=False, tenant_id=tid,
    )
    db_session.add_all([admin_user, profesor_user, alumno_user])
    await db_session.flush()
    for u in (admin_user, profesor_user, alumno_user):
        await db_session.refresh(u)
    admin_id = admin_user.id
    profesor_id = profesor_user.id
    alumno_id = alumno_user.id

    # Roles
    rol_admin = Rol(tenant_id=tid, nombre="ADMIN", descripcion="Administrador")
    rol_profesor = Rol(tenant_id=tid, nombre="PROFESOR", descripcion="Profesor")
    db_session.add_all([rol_admin, rol_profesor])
    await db_session.flush()
    await db_session.refresh(rol_admin)
    await db_session.refresh(rol_profesor)
    rol_admin_id = rol_admin.id
    rol_profesor_id = rol_profesor.id

    # Permisos
    p_confirmar = Permiso(
        tenant_id=tid, codigo="comunicacion:confirmar_aviso",
        modulo="comunicacion", descripcion="Confirmar aviso",
    )
    p_importar = Permiso(
        tenant_id=tid, codigo="calificaciones:importar",
        modulo="calificaciones", descripcion="Importar calificaciones",
    )
    p_auditoria = Permiso(
        tenant_id=tid, codigo="auditoria:ver",
        modulo="auditoria", descripcion="Ver auditoría",
    )
    db_session.add_all([p_confirmar, p_importar, p_auditoria])
    await db_session.flush()
    for p in (p_confirmar, p_importar, p_auditoria):
        await db_session.refresh(p)
    p_confirmar_id = p_confirmar.id
    p_importar_id = p_importar.id
    p_auditoria_id = p_auditoria.id

    # RolPermiso matrix
    db_session.add_all([
        RolPermiso(tenant_id=tid, rol_id=rol_admin_id, permiso_id=p_confirmar_id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_admin_id, permiso_id=p_importar_id,  scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_admin_id, permiso_id=p_auditoria_id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_profesor_id, permiso_id=p_confirmar_id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_profesor_id, permiso_id=p_importar_id,  scope="own"),
    ])
    await db_session.flush()

    # UserRol — alumno deliberately has no role
    db_session.add_all([
        UserRol(tenant_id=tid, user_id=admin_id,   rol_id=rol_admin_id),
        UserRol(tenant_id=tid, user_id=profesor_id, rol_id=rol_profesor_id),
    ])
    await db_session.flush()
    await db_session.commit()

    return {
        "tenant_id":       tid,
        "admin_user_id":   admin_id,
        "profesor_user_id": profesor_id,
        "alumno_user_id":  alumno_id,
        "rol_admin_id":    rol_admin_id,
        "rol_profesor_id": rol_profesor_id,
    }


# ── get_user_permissions ──────────────────────────────────────────────────────


class TestGetUserPermissions:
    """Unit tests for get_user_permissions() — server-side permission resolver."""

    async def test_single_role_returns_assigned_permissions(self, db_session, rbac_db):
        """PROFESOR returns exactly the permissions defined in its RolPermiso entries."""
        d = rbac_db
        perms = await get_user_permissions(d["profesor_user_id"], d["tenant_id"], db_session)

        assert perms.get("comunicacion:confirmar_aviso") == "all"
        assert perms.get("calificaciones:importar") == "own"
        assert "auditoria:ver" not in perms

    async def test_user_without_roles_returns_empty_dict(self, db_session, rbac_db):
        """User with no UserRol entries has no effective permissions."""
        d = rbac_db
        perms = await get_user_permissions(d["alumno_user_id"], d["tenant_id"], db_session)

        assert perms == {}

    async def test_role_union_all_wins_over_own(self, db_session, rbac_db):
        """
        When two roles grant the same permission with different scopes, 'all' wins.
        Covers spec: 'If a permission appears with both all and own, all wins.'
        """
        from app.models.user_rol import UserRol

        d = rbac_db
        # profesor has calificaciones:importar via PROFESOR (own).
        # Adding ADMIN (all) must promote the effective scope to 'all'.
        db_session.add(UserRol(
            tenant_id=d["tenant_id"],
            user_id=d["profesor_user_id"],
            rol_id=d["rol_admin_id"],
        ))
        await db_session.commit()

        perms = await get_user_permissions(d["profesor_user_id"], d["tenant_id"], db_session)
        assert perms["calificaciones:importar"] == "all"

    async def test_soft_deleted_user_rol_excluded(self, db_session, rbac_db):
        """Soft-deleting a UserRol removes that role's permissions from the result."""
        from app.models.user_rol import UserRol

        d = rbac_db
        result = await db_session.execute(
            select(UserRol).where(
                UserRol.user_id == d["admin_user_id"],
                UserRol.deleted_at.is_(None),
            )
        )
        user_rol = result.scalar_one()
        user_rol.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db_session.commit()

        perms = await get_user_permissions(d["admin_user_id"], d["tenant_id"], db_session)
        assert perms == {}


# ── check_permission ──────────────────────────────────────────────────────────


class TestCheckPermission:
    """Unit tests for check_permission() — single-permission check."""

    async def test_granted_with_scope_all(self, db_session, rbac_db):
        """ADMIN has auditoria:ver → granted=True, scope='all'."""
        d = rbac_db
        result = await check_permission(
            d["admin_user_id"], d["tenant_id"], "auditoria:ver", db_session,
        )
        assert result.granted is True
        assert result.scope == "all"

    async def test_granted_with_scope_own(self, db_session, rbac_db):
        """PROFESOR has calificaciones:importar → granted=True, scope='own'."""
        d = rbac_db
        result = await check_permission(
            d["profesor_user_id"], d["tenant_id"], "calificaciones:importar", db_session,
        )
        assert result.granted is True
        assert result.scope == "own"

    async def test_not_granted_for_user_without_role(self, db_session, rbac_db):
        """User with no roles is denied any permission (granted=False, scope=None)."""
        d = rbac_db
        result = await check_permission(
            d["alumno_user_id"], d["tenant_id"], "calificaciones:importar", db_session,
        )
        assert result.granted is False
        assert result.scope is None

    async def test_all_wins_when_two_roles_grant_same_permission(self, db_session, rbac_db):
        """Adding a second role with 'all' scope upgrades the effective scope to 'all'."""
        from app.models.user_rol import UserRol

        d = rbac_db
        db_session.add(UserRol(
            tenant_id=d["tenant_id"],
            user_id=d["profesor_user_id"],
            rol_id=d["rol_admin_id"],
        ))
        await db_session.commit()

        result = await check_permission(
            d["profesor_user_id"], d["tenant_id"], "calificaciones:importar", db_session,
        )
        assert result.granted is True
        assert result.scope == "all"

    async def test_permission_absent_from_all_roles_returns_not_granted(self, db_session, rbac_db):
        """A permission not assigned to any of the user's roles is denied."""
        d = rbac_db
        result = await check_permission(
            d["profesor_user_id"], d["tenant_id"], "estructura_academica:gestionar", db_session,
        )
        assert result.granted is False
        assert result.scope is None


# ── require_permission HTTP guard ─────────────────────────────────────────────


class TestRequirePermissionHTTP:
    """Integration tests for require_permission() via GET /api/auth/me."""

    async def _login(self, client: AsyncClient, email: str) -> dict:
        resp = await client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE, "email": email, "password": USER_PASS,
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        return resp.json()

    async def test_user_with_permission_passes_guard(self, async_client, rbac_db):
        """ADMIN (has comunicacion:confirmar_aviso) can access GET /api/auth/me."""
        tokens = await self._login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200

    async def test_profesor_with_permission_also_passes_guard(self, async_client, rbac_db):
        """PROFESOR also has comunicacion:confirmar_aviso → /me succeeds."""
        tokens = await self._login(async_client, PROFESOR_EMAIL)
        resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200

    async def test_user_without_role_gets_403(self, async_client, rbac_db):
        """User with no roles gets HTTP 403 and the missing permission is named."""
        tokens = await self._login(async_client, ALUMNO_EMAIL)
        resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 403
        assert "comunicacion:confirmar_aviso" in resp.json()["detail"]

    async def test_anonymous_request_gets_401(self, async_client, rbac_db):
        """Request without JWT gets 401 — guard rejects before any permission check."""
        resp = await async_client.get("/api/auth/me")
        assert resp.status_code == 401


# ── JWT roles claim ───────────────────────────────────────────────────────────


class TestJWTRolesFromUserRol:
    """Verify that the JWT roles claim reflects UserRol state at login and refresh."""

    async def _login(self, client: AsyncClient, email: str) -> dict:
        resp = await client.post("/api/auth/login", json={
            "tenant_code": TENANT_CODE, "email": email, "password": USER_PASS,
        })
        assert resp.status_code == 200
        return resp.json()

    def _decode(self, token: str) -> dict:
        return pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

    async def test_login_jwt_contains_assigned_role(self, async_client, rbac_db):
        """JWT after login has roles populated from UserRol, not hardcoded []."""
        tokens = await self._login(async_client, ADMIN_EMAIL)
        payload = self._decode(tokens["access_token"])
        assert payload["roles"] == ["ADMIN"]

    async def test_login_jwt_empty_roles_for_user_without_assignment(self, async_client, rbac_db):
        """User with no UserRol entry gets roles=[] in the JWT."""
        tokens = await self._login(async_client, ALUMNO_EMAIL)
        payload = self._decode(tokens["access_token"])
        assert payload["roles"] == []

    async def test_refresh_jwt_reflects_current_roles(self, async_client, rbac_db):
        """New JWT after refresh contains up-to-date roles from UserRol."""
        tokens = await self._login(async_client, PROFESOR_EMAIL)
        resp = await async_client.post("/api/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert resp.status_code == 200
        payload = self._decode(resp.json()["access_token"])
        assert "PROFESOR" in payload["roles"]
