"""C-05 audit-log — integration and unit tests.

Covers:
- RN-24: action code catalog validation (AuditService.log() rejects unknown codes)
- DB-level append-only enforcement (PostgreSQL RULEs block UPDATE and DELETE)
- Impersonation endpoints: JWT claims, permission guard, 404/400 edge cases
- Audit trail: INICIAR/FINALIZAR events attributed to real actor
- auditoria:ver permission matrix and scope enforcement
- Filters and pagination
"""

from uuid import UUID

import jwt as pyjwt
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import IMPERSONACION_FINALIZAR, IMPERSONACION_INICIAR, VALID_ACTION_CODES
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.auth import CurrentUser
from app.services.audit_service import AuditService

TENANT_CODE = "audit-test"
USER_PASS = "Admin123!"

ADMIN_EMAIL = "audit.admin@test.edu.ar"
COORDINADOR_EMAIL = "audit.coord@test.edu.ar"
FINANZAS_EMAIL = "audit.finanzas@test.edu.ar"
ALUMNO_EMAIL = "audit.alumno@test.edu.ar"
PROFESOR_EMAIL = "audit.profesor@test.edu.ar"
TARGET_EMAIL = "audit.target@test.edu.ar"


# ── Fixture ───────────────────────────────────────────────────────────────────


async def _truncate_audit(session: AsyncSession) -> None:
    """TRUNCATE audit_log — bypasses PostgreSQL RULEs for test cleanup."""
    await session.execute(text("TRUNCATE TABLE audit_log"))
    await session.commit()


@pytest_asyncio.fixture
async def audit_db(db_session: AsyncSession) -> dict:
    """Seed a full audit-test environment.

    Users  : admin, coordinador, finanzas, alumno, profesor, target
    Roles  : ADMIN, COORDINADOR, FINANZAS, ALUMNO
    Perms  : impersonacion:usar, auditoria:ver, comunicacion:confirmar_aviso
    Matrix :
      ADMIN       → impersonacion:usar(all), auditoria:ver(all), comunicacion(all)
      COORDINADOR → auditoria:ver(own), comunicacion(all)
      FINANZAS    → auditoria:ver(all), comunicacion(all)
      ALUMNO      → comunicacion(all)
    """
    from app.models.permiso import Permiso
    from app.models.rol import Rol
    from app.models.rol_permiso import RolPermiso
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.user_rol import UserRol

    # Clean slate — TRUNCATE audit_log first (RESTRICT FK prevents deleting users with audit rows)
    await _truncate_audit(db_session)
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
    tenant = Tenant(codigo=TENANT_CODE, nombre="Audit Test Tenant")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    tid = tenant.id

    # Users
    def _user(email: str) -> User:
        return User(
            email=email, password_hash=hash_password(USER_PASS),
            nombre="Test", apellido="User",
            is_active=True, is_2fa_enabled=False, tenant_id=tid,
        )

    admin = _user(ADMIN_EMAIL)
    coord = _user(COORDINADOR_EMAIL)
    finanzas = _user(FINANZAS_EMAIL)
    alumno = _user(ALUMNO_EMAIL)
    profesor = _user(PROFESOR_EMAIL)
    target = _user(TARGET_EMAIL)
    db_session.add_all([admin, coord, finanzas, alumno, profesor, target])
    await db_session.flush()
    for u in (admin, coord, finanzas, alumno, profesor, target):
        await db_session.refresh(u)
    admin_id = admin.id
    coord_id = coord.id
    finanzas_id = finanzas.id
    alumno_id = alumno.id
    target_id = target.id

    # Roles
    rol_admin = Rol(tenant_id=tid, nombre="ADMIN", descripcion="Administrador")
    rol_coord = Rol(tenant_id=tid, nombre="COORDINADOR", descripcion="Coordinador")
    rol_finanzas = Rol(tenant_id=tid, nombre="FINANZAS", descripcion="Finanzas")
    rol_alumno = Rol(tenant_id=tid, nombre="ALUMNO", descripcion="Alumno")
    db_session.add_all([rol_admin, rol_coord, rol_finanzas, rol_alumno])
    await db_session.flush()
    for r in (rol_admin, rol_coord, rol_finanzas, rol_alumno):
        await db_session.refresh(r)

    # Permisos
    p_imp = Permiso(tenant_id=tid, codigo="impersonacion:usar", modulo="impersonacion", descripcion="Impersonar")
    p_aud = Permiso(tenant_id=tid, codigo="auditoria:ver", modulo="auditoria", descripcion="Ver auditoría")
    p_com = Permiso(tenant_id=tid, codigo="comunicacion:confirmar_aviso", modulo="comunicacion", descripcion="Confirmar aviso")
    db_session.add_all([p_imp, p_aud, p_com])
    await db_session.flush()
    for p in (p_imp, p_aud, p_com):
        await db_session.refresh(p)

    # Matrix
    db_session.add_all([
        # ADMIN: all permissions
        RolPermiso(tenant_id=tid, rol_id=rol_admin.id, permiso_id=p_imp.id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_admin.id, permiso_id=p_aud.id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_admin.id, permiso_id=p_com.id, scope="all"),
        # COORDINADOR: auditoria:ver (own), confirmar (all)
        RolPermiso(tenant_id=tid, rol_id=rol_coord.id, permiso_id=p_aud.id, scope="own"),
        RolPermiso(tenant_id=tid, rol_id=rol_coord.id, permiso_id=p_com.id, scope="all"),
        # FINANZAS: auditoria:ver (all), confirmar (all)
        RolPermiso(tenant_id=tid, rol_id=rol_finanzas.id, permiso_id=p_aud.id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_finanzas.id, permiso_id=p_com.id, scope="all"),
        # ALUMNO: confirmar only
        RolPermiso(tenant_id=tid, rol_id=rol_alumno.id, permiso_id=p_com.id, scope="all"),
    ])
    await db_session.flush()

    # UserRol — profesor deliberately has no role (anonymous-like)
    db_session.add_all([
        UserRol(tenant_id=tid, user_id=admin_id,    rol_id=rol_admin.id),
        UserRol(tenant_id=tid, user_id=coord_id,    rol_id=rol_coord.id),
        UserRol(tenant_id=tid, user_id=finanzas_id, rol_id=rol_finanzas.id),
        UserRol(tenant_id=tid, user_id=alumno_id,   rol_id=rol_alumno.id),
    ])
    await db_session.flush()
    await db_session.commit()

    return {
        "tenant_id":    tid,
        "admin_id":     admin_id,
        "coord_id":     coord_id,
        "finanzas_id":  finanzas_id,
        "alumno_id":    alumno_id,
        "target_id":    target_id,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, email: str) -> dict:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": TENANT_CODE, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()


def _decode(token: str) -> dict:
    return pyjwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


def _make_ctx(user_id: UUID, tenant_id: UUID, roles: list[str], impersonado_id: UUID | None = None) -> CurrentUser:
    return CurrentUser(user_id=user_id, tenant_id=tenant_id, roles=roles, impersonado_id=impersonado_id)


# ── Catalog validation (RN-24) ────────────────────────────────────────────────


class TestActionCodeCatalog:

    def test_valid_action_codes_is_frozenset(self):
        assert isinstance(VALID_ACTION_CODES, frozenset)
        assert IMPERSONACION_INICIAR in VALID_ACTION_CODES
        assert IMPERSONACION_FINALIZAR in VALID_ACTION_CODES

    async def test_log_rejects_invalid_action_code(self, db_session: AsyncSession, audit_db: dict):
        d = audit_db
        ctx = _make_ctx(d["admin_id"], d["tenant_id"], ["ADMIN"])
        service = AuditService(db_session)
        with pytest.raises(ValueError, match="Unknown audit action code"):
            await service.log(current_user=ctx, accion="CODIGO_ARBITRARIO_INVALIDO")

        # Verify no row was inserted
        repo = AuditLogRepository(db_session, d["tenant_id"])
        rows, total = await repo.list()
        assert total == 0


# ── DB-level append-only (PostgreSQL RULEs) ───────────────────────────────────


class TestAppendOnlyDB:

    async def test_db_rule_blocks_update(self, db_session: AsyncSession, audit_db: dict):
        d = audit_db
        ctx = _make_ctx(d["admin_id"], d["tenant_id"], ["ADMIN"])
        service = AuditService(db_session)
        await service.log(current_user=ctx, accion=IMPERSONACION_INICIAR)
        await db_session.commit()

        repo = AuditLogRepository(db_session, d["tenant_id"])
        rows, _ = await repo.list()
        assert len(rows) == 1
        entry_id = rows[0].id

        result = await db_session.execute(
            text("UPDATE audit_log SET accion = 'TAMPERED' WHERE id = :id"),
            {"id": entry_id},
        )
        await db_session.commit()
        assert result.rowcount == 0

        rows2, _ = await repo.list()
        assert rows2[0].accion == IMPERSONACION_INICIAR

    async def test_db_rule_blocks_delete(self, db_session: AsyncSession, audit_db: dict):
        d = audit_db
        ctx = _make_ctx(d["admin_id"], d["tenant_id"], ["ADMIN"])
        service = AuditService(db_session)
        await service.log(current_user=ctx, accion=IMPERSONACION_INICIAR)
        await db_session.commit()

        repo = AuditLogRepository(db_session, d["tenant_id"])
        rows, _ = await repo.list()
        assert len(rows) == 1
        entry_id = rows[0].id

        result = await db_session.execute(
            text("DELETE FROM audit_log WHERE id = :id"),
            {"id": entry_id},
        )
        await db_session.commit()
        assert result.rowcount == 0

        rows2, total = await repo.list()
        assert total == 1
        assert rows2[0].id == entry_id

    def test_audit_log_repository_has_no_mutating_methods(self):
        for method in ("update", "delete", "soft_delete", "hard_delete"):
            assert not hasattr(AuditLogRepository, method)


# ── Impersonation: JWT claims ─────────────────────────────────────────────────


class TestImpersonationJWT:

    async def test_normal_login_jwt_has_no_impersonado_id(self, async_client: AsyncClient, audit_db: dict):
        tokens = await _login(async_client, ADMIN_EMAIL)
        payload = _decode(tokens["access_token"])
        assert "impersonado_id" not in payload

    async def test_current_user_impersonado_id_is_none_on_normal_login(
        self, async_client: AsyncClient, audit_db: dict
    ):
        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("impersonado_id") is None


# ── Impersonation: POST /auth/impersonate ────────────────────────────────────


class TestStartImpersonation:

    async def _start(self, client: AsyncClient, admin_token: str, target_id: UUID) -> dict:
        resp = await client.post(
            "/api/auth/impersonate",
            json={"target_user_id": str(target_id)},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        return resp

    async def test_start_impersonation_returns_200_with_impersonado_id(
        self, async_client: AsyncClient, audit_db: dict
    ):
        d = audit_db
        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await self._start(async_client, tokens["access_token"], d["target_id"])
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["impersonado_id"] == str(d["target_id"])

    async def test_impersonation_jwt_carries_impersonado_id_claim(
        self, async_client: AsyncClient, audit_db: dict
    ):
        d = audit_db
        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await self._start(async_client, tokens["access_token"], d["target_id"])
        assert resp.status_code == 200
        payload = _decode(resp.json()["access_token"])
        assert payload["impersonado_id"] == str(d["target_id"])

    async def test_impersonation_logs_iniciar_attributed_to_real_actor(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        d = audit_db
        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await self._start(async_client, tokens["access_token"], d["target_id"])
        assert resp.status_code == 200

        repo = AuditLogRepository(db_session, d["tenant_id"])
        rows, total = await repo.list(accion_filter=IMPERSONACION_INICIAR)
        assert total == 1
        assert rows[0].actor_id == d["admin_id"]
        assert rows[0].impersonado_id == d["target_id"]

    async def test_impersonate_target_not_found_returns_404(
        self, async_client: AsyncClient, audit_db: dict
    ):
        tokens = await _login(async_client, ADMIN_EMAIL)
        fake_id = "00000000-0000-0000-0000-000000000099"
        resp = await self._start(async_client, tokens["access_token"], UUID(fake_id))
        assert resp.status_code == 404

    async def test_impersonate_inactive_target_returns_400(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        d = audit_db
        await db_session.execute(
            text('UPDATE "user" SET is_active = FALSE WHERE id = :id'),
            {"id": d["target_id"]},
        )
        await db_session.commit()

        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await self._start(async_client, tokens["access_token"], d["target_id"])
        assert resp.status_code == 400

    async def test_impersonate_requires_impersonacion_usar_permission(
        self, async_client: AsyncClient, audit_db: dict
    ):
        d = audit_db
        # PROFESOR has no roles and therefore no impersonacion:usar
        tokens = await _login(async_client, PROFESOR_EMAIL)
        resp = await self._start(async_client, tokens["access_token"], d["target_id"])
        assert resp.status_code == 403

    async def test_impersonate_unauthenticated_returns_401(
        self, async_client: AsyncClient, audit_db: dict
    ):
        d = audit_db
        resp = await async_client.post(
            "/api/auth/impersonate",
            json={"target_user_id": str(d["target_id"])},
        )
        assert resp.status_code == 401


# ── Impersonation: POST /auth/impersonate/end ─────────────────────────────────


class TestEndImpersonation:

    async def _get_impersonating_token(
        self, client: AsyncClient, audit_db: dict
    ) -> tuple[str, str]:
        """Log in as admin, start impersonation, return (admin_token, impersonation_token)."""
        tokens = await _login(client, ADMIN_EMAIL)
        resp = await client.post(
            "/api/auth/impersonate",
            json={"target_user_id": str(audit_db["target_id"])},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        return tokens["access_token"], resp.json()["access_token"]

    async def test_end_returns_clean_jwt_without_impersonado_id(
        self, async_client: AsyncClient, audit_db: dict
    ):
        _, imp_token = await self._get_impersonating_token(async_client, audit_db)
        resp = await async_client.post(
            "/api/auth/impersonate/end",
            headers={"Authorization": f"Bearer {imp_token}"},
        )
        assert resp.status_code == 200
        clean_token = resp.json()["access_token"]
        payload = _decode(clean_token)
        assert "impersonado_id" not in payload

    async def test_end_logs_finalizar_attributed_to_real_actor(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        d = audit_db
        _, imp_token = await self._get_impersonating_token(async_client, audit_db)
        resp = await async_client.post(
            "/api/auth/impersonate/end",
            headers={"Authorization": f"Bearer {imp_token}"},
        )
        assert resp.status_code == 200

        repo = AuditLogRepository(db_session, d["tenant_id"])
        rows, total = await repo.list(accion_filter=IMPERSONACION_FINALIZAR)
        assert total == 1
        assert rows[0].actor_id == d["admin_id"]
        assert rows[0].impersonado_id == d["target_id"]

    async def test_end_without_active_session_returns_400(
        self, async_client: AsyncClient, audit_db: dict
    ):
        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/auth/impersonate/end",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 400
        assert "No active impersonation session" in resp.json()["detail"]

    async def test_actions_under_impersonation_attribute_to_real_actor(
        self, db_session: AsyncSession, audit_db: dict
    ):
        d = audit_db
        ctx = _make_ctx(
            d["admin_id"], d["tenant_id"], ["ADMIN"],
            impersonado_id=d["target_id"],
        )
        service = AuditService(db_session)
        await service.log(current_user=ctx, accion=IMPERSONACION_INICIAR)
        await db_session.commit()

        repo = AuditLogRepository(db_session, d["tenant_id"])
        rows, _ = await repo.list()
        assert rows[0].actor_id == d["admin_id"]
        assert rows[0].impersonado_id == d["target_id"]
        # The impersonated user's ID never appears as actor_id
        assert rows[0].actor_id != d["target_id"]


# ── auditoria:ver permission matrix ───────────────────────────────────────────


class TestAuditoriaVer:

    async def _seed_entries(
        self, db_session: AsyncSession, audit_db: dict, count: int = 3, actor_id: UUID | None = None
    ) -> None:
        d = audit_db
        used_id = actor_id or d["admin_id"]
        ctx = _make_ctx(used_id, d["tenant_id"], ["ADMIN"])
        service = AuditService(db_session)
        for _ in range(count):
            await service.log(current_user=ctx, accion=IMPERSONACION_INICIAR)
        await db_session.commit()

    async def test_admin_can_list_audit_log(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        await self._seed_entries(db_session, audit_db)
        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 3

    async def test_finanzas_can_list_audit_log(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        await self._seed_entries(db_session, audit_db)
        tokens = await _login(async_client, FINANZAS_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200

    async def test_coordinador_sees_only_own_entries(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        d = audit_db
        # Admin creates 3 entries, coord creates 2 entries
        await self._seed_entries(db_session, audit_db, count=3, actor_id=d["admin_id"])
        await self._seed_entries(db_session, audit_db, count=2, actor_id=d["coord_id"])

        tokens = await _login(async_client, COORDINADOR_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        for item in body["items"]:
            assert item["actor_id"] == str(d["coord_id"])

    async def test_alumno_receives_403(
        self, async_client: AsyncClient, audit_db: dict
    ):
        tokens = await _login(async_client, ALUMNO_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 403

    async def test_list_filter_by_accion(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        d = audit_db
        ctx_admin = _make_ctx(d["admin_id"], d["tenant_id"], ["ADMIN"])
        service = AuditService(db_session)
        await service.log(current_user=ctx_admin, accion=IMPERSONACION_INICIAR)
        await service.log(current_user=ctx_admin, accion=IMPERSONACION_FINALIZAR)
        await db_session.commit()

        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            f"/api/v1/auditoria?accion={IMPERSONACION_INICIAR}",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        for item in body["items"]:
            assert item["accion"] == IMPERSONACION_INICIAR

    async def test_list_pagination(
        self, async_client: AsyncClient, db_session: AsyncSession, audit_db: dict
    ):
        d = audit_db
        ctx = _make_ctx(d["admin_id"], d["tenant_id"], ["ADMIN"])
        service = AuditService(db_session)
        for _ in range(15):
            await service.log(current_user=ctx, accion=IMPERSONACION_INICIAR)
        await db_session.commit()

        tokens = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria?page=2&page_size=10",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 5
        assert body["total"] == 15
        assert body["page"] == 2
        assert body["page_size"] == 10
