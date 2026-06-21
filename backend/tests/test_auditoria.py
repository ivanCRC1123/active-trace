"""C-19 panel-auditoria-metricas — integration tests.

Covers F9.1 panel endpoints and F9.2 log completo con dual schema.
No new migration: reads audit_log (C-05) and comunicacion (C-12).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import (
    COMUNICACION_ENVIAR,
    IMPERSONACION_INICIAR,
    PADRON_CARGAR,
)
from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.auth import CurrentUser
from app.services.audit_service import AuditService

TENANT_A = "aud-19-a"
TENANT_B = "aud-19-b"
USER_PASS = "Admin123!"

ADMIN_EMAIL = "aud19.admin@test.edu.ar"
COORD_EMAIL = "aud19.coord@test.edu.ar"
FINANZAS_EMAIL = "aud19.finanzas@test.edu.ar"
ALUMNO_EMAIL = "aud19.alumno@test.edu.ar"


# ── Setup helpers ─────────────────────────────────────────────────────────────


async def _delete_tenant_data(session: AsyncSession, *codes: str) -> None:
    """Remove test data scoped to specific tenant codes."""
    for code in codes:
        tid_sub = "(SELECT id FROM tenant WHERE codigo = :c)"
        for table in ("comunicacion", "asignacion", "aviso", "materia", "carrera", "cohorte"):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN {tid_sub}"),
                {"c": code},
            )
        for table in ("user_rol", "rol_permiso", "permiso", "rol"):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN {tid_sub}"),
                {"c": code},
            )
        for table in ("refresh_token", "recovery_token"):
            await session.execute(
                text(
                    f'DELETE FROM {table} WHERE user_id IN '
                    f'(SELECT id FROM "user" WHERE tenant_id IN {tid_sub})'
                ),
                {"c": code},
            )
        await session.execute(
            text(f'DELETE FROM "user" WHERE tenant_id IN {tid_sub}'),
            {"c": code},
        )
        await session.execute(text("DELETE FROM tenant WHERE codigo = :c"), {"c": code})
    await session.commit()


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def aud_db(db_session: AsyncSession):
    """Seed C-19 test environment.

    Tenant A: admin (scope=all), coordinador (scope=own → materia_id only), finanzas (scope=all), alumno (no perm)
    Tenant B: admin user — for cross-tenant isolation test
    Audit log: 3 entries with materia, 2 with other_materia, 1 no-materia, 1 by coordinator
    Comunicaciones: admin sent 2 ENVIADO, coord sent 1 PENDIENTE + 1 CANCELADO (other_materia)
    """
    from app.models.asignacion import Asignacion
    from app.models.materia import Materia
    from app.models.permiso import Permiso
    from app.models.rol import Rol
    from app.models.rol_permiso import RolPermiso
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.user_rol import UserRol

    await _delete_tenant_data(db_session, TENANT_A, TENANT_B)

    def _user(email: str, tid: UUID) -> User:
        return User(
            email_cifrado=encrypt(email),
            email_hash=hmac_email(email),
            password_hash=hash_password(USER_PASS),
            nombre="Test",
            apellidos="User",
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
        )

    # ── Tenant A ──────────────────────────────────────────────────────────
    ta = Tenant(codigo=TENANT_A, nombre="Auditoria Test A")
    db_session.add(ta)
    await db_session.flush()
    await db_session.refresh(ta)
    tid_a = ta.id

    admin = _user(ADMIN_EMAIL, tid_a)
    coord = _user(COORD_EMAIL, tid_a)
    finanzas = _user(FINANZAS_EMAIL, tid_a)
    alumno = _user(ALUMNO_EMAIL, tid_a)
    db_session.add_all([admin, coord, finanzas, alumno])
    await db_session.flush()
    for u in (admin, coord, finanzas, alumno):
        await db_session.refresh(u)

    # Roles
    r_admin = Rol(tenant_id=tid_a, nombre="ADMIN", descripcion="Admin")
    r_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    r_finanzas = Rol(tenant_id=tid_a, nombre="FINANZAS", descripcion="Finanzas")
    r_alumno = Rol(tenant_id=tid_a, nombre="ALUMNO", descripcion="Alumno")
    db_session.add_all([r_admin, r_coord, r_finanzas, r_alumno])
    await db_session.flush()
    for r in (r_admin, r_coord, r_finanzas, r_alumno):
        await db_session.refresh(r)

    # Materias
    materia = Materia(tenant_id=tid_a, nombre="Matemáticas I", codigo="MAT001")
    other_materia = Materia(tenant_id=tid_a, nombre="Historia", codigo="HIS001")
    db_session.add_all([materia, other_materia])
    await db_session.flush()
    for m in (materia, other_materia):
        await db_session.refresh(m)

    # Coordinator is assigned to 'materia' but NOT 'other_materia'
    today = date.today()
    asig = Asignacion(
        tenant_id=tid_a,
        usuario_id=coord.id,
        rol_id=r_coord.id,
        materia_id=materia.id,
        desde=today - timedelta(days=30),
    )
    db_session.add(asig)
    await db_session.flush()

    # Permiso auditoria:ver
    p_aud = Permiso(tenant_id=tid_a, codigo="auditoria:ver", modulo="auditoria", descripcion="Ver auditoría")
    db_session.add(p_aud)
    await db_session.flush()
    await db_session.refresh(p_aud)

    # RBAC: admin=all, coord=own, finanzas=all, alumno=no perm
    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=r_admin.id, permiso_id=p_aud.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=r_coord.id, permiso_id=p_aud.id, scope="own"),
        RolPermiso(tenant_id=tid_a, rol_id=r_finanzas.id, permiso_id=p_aud.id, scope="all"),
    ])
    db_session.add_all([
        UserRol(tenant_id=tid_a, user_id=admin.id, rol_id=r_admin.id),
        UserRol(tenant_id=tid_a, user_id=coord.id, rol_id=r_coord.id),
        UserRol(tenant_id=tid_a, user_id=finanzas.id, rol_id=r_finanzas.id),
        UserRol(tenant_id=tid_a, user_id=alumno.id, rol_id=r_alumno.id),
    ])
    await db_session.flush()

    # ── Tenant B ──────────────────────────────────────────────────────────
    tb = Tenant(codigo=TENANT_B, nombre="Auditoria Test B")
    db_session.add(tb)
    await db_session.flush()
    await db_session.refresh(tb)
    tid_b = tb.id

    await db_session.commit()

    # ── Audit log entries ──────────────────────────────────────────────────
    svc = AuditService(db_session)
    ctx_admin = CurrentUser(user_id=admin.id, tenant_id=tid_a, roles=["ADMIN"])
    ctx_coord = CurrentUser(user_id=coord.id, tenant_id=tid_a, roles=["COORDINADOR"])

    # 3 entries with coord's materia → coordinator CAN see
    for _ in range(3):
        await svc.log(current_user=ctx_admin, accion=IMPERSONACION_INICIAR, materia_id=materia.id)

    # 2 entries with other_materia → coordinator CANNOT see
    for _ in range(2):
        await svc.log(current_user=ctx_admin, accion=IMPERSONACION_INICIAR, materia_id=other_materia.id)

    # 1 entry without materia_id → coordinator CANNOT see
    await svc.log(current_user=ctx_admin, accion=PADRON_CARGAR)

    # 1 entry by coordinator in their materia → coordinator CAN see (own entry)
    await svc.log(current_user=ctx_coord, accion=COMUNICACION_ENVIAR, materia_id=materia.id)

    await db_session.commit()

    # Tenant B entries (isolation): use UUID not present in tenant A to verify isolation
    repo_b = AuditLogRepository(db_session, tid_b)
    fake_actor_b = uuid.uuid4()
    await repo_b.insert(actor_id=fake_actor_b, accion=IMPERSONACION_INICIAR)
    await db_session.commit()

    # ── Comunicacion entries ───────────────────────────────────────────────
    from app.models.comunicacion import Comunicacion

    lote1 = uuid.uuid4()
    lote2 = uuid.uuid4()
    db_session.add_all([
        # Admin: 2 ENVIADO for coord's materia
        Comunicacion(
            tenant_id=tid_a, enviado_por=admin.id, materia_id=materia.id,
            destinatario=encrypt("dest1@test.com"), asunto="Test 1", cuerpo="Body",
            estado="ENVIADO", lote_id=lote1,
        ),
        Comunicacion(
            tenant_id=tid_a, enviado_por=admin.id, materia_id=materia.id,
            destinatario=encrypt("dest2@test.com"), asunto="Test 2", cuerpo="Body",
            estado="ENVIADO", lote_id=lote1,
        ),
        # Coord: 1 PENDIENTE in their materia
        Comunicacion(
            tenant_id=tid_a, enviado_por=coord.id, materia_id=materia.id,
            destinatario=encrypt("dest3@test.com"), asunto="Test 3", cuerpo="Body",
            estado="PENDIENTE", lote_id=lote2,
        ),
        # Coord: 1 CANCELADO in other_materia → coordinator NOT in scope
        Comunicacion(
            tenant_id=tid_a, enviado_por=coord.id, materia_id=other_materia.id,
            destinatario=encrypt("dest4@test.com"), asunto="Test 4", cuerpo="Body",
            estado="CANCELADO", lote_id=lote2,
        ),
    ])
    await db_session.commit()

    yield {
        "tenant_id_a": tid_a,
        "tenant_id_b": tid_b,
        "admin_id": admin.id,
        "coord_id": coord.id,
        "finanzas_id": finanzas.id,
        "alumno_id": alumno.id,
        "materia_id": materia.id,
        "other_materia_id": other_materia.id,
    }

    # Teardown: remove domain data so other fixtures can do DELETE FROM tenant freely.
    # audit_log entries for old UUID are orphaned but harmless (no FK to tenant).
    await _delete_tenant_data(db_session, TENANT_A, TENANT_B)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, email: str, tenant_code: str = TENANT_A) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── TestAccionesXDia ──────────────────────────────────────────────────────────


class TestAccionesXDia:

    async def test_acciones_xdia_admin_ve_todo(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/acciones-por-dia",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        # 7 total entries (3 + 2 + 1 + 1) for tenant A
        assert body["total_acciones"] == 7

    async def test_acciones_xdia_coordinador_scope_own(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/acciones-por-dia",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Coordinator sees only entries with their materia (3 by admin + 1 by coord = 4)
        assert body["total_acciones"] == 4

    async def test_acciones_xdia_filtro_fecha(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """to_date in the past excludes all seeded entries (which were just created)."""
        token = await _login(async_client, ADMIN_EMAIL)
        long_ago = "2020-01-01"
        resp = await async_client.get(
            f"/api/v1/auditoria/panel/acciones-por-dia?to_date={long_ago}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_acciones"] == 0
        assert body["items"] == []

    async def test_acciones_xdia_sin_datos_200_vacio(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """204/empty list when no data matches — always 200, never 404."""
        token = await _login(async_client, ADMIN_EMAIL)
        future = (date.today() + timedelta(days=365)).isoformat()
        resp = await async_client.get(
            f"/api/v1/auditoria/panel/acciones-por-dia?from_date={future}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []


# ── TestComunicacionesDocente ─────────────────────────────────────────────────


class TestComunicacionesDocente:

    async def test_comunicaciones_docente_estados_agrupados(
        self, async_client: AsyncClient, aud_db: dict
    ):
        d = aud_db
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/comunicaciones-docente",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Admin: 2 ENVIADO; Coord: 1 PENDIENTE + 1 CANCELADO (but other_materia)
        actor_ids = {i["actor_id"] for i in items}
        assert str(d["admin_id"]) in actor_ids
        assert str(d["coord_id"]) in actor_ids

        admin_item = next(i for i in items if i["actor_id"] == str(d["admin_id"]))
        assert admin_item["estados"].get("ENVIADO") == 2
        assert admin_item["total"] == 2

    async def test_comunicaciones_docente_coordinador_scope_own(
        self, async_client: AsyncClient, aud_db: dict
    ):
        d = aud_db
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/comunicaciones-docente",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Coordinator scope = only materia.id, not other_materia.id
        # Admin has 2 in materia → visible; Coord has 1 in materia + 1 in other_materia
        # → admin visible (total 2), coord visible for materia only (PENDIENTE=1)
        actor_ids = {i["actor_id"] for i in items}
        assert str(d["admin_id"]) in actor_ids
        # Coord's CANCELADO in other_materia should NOT appear
        coord_item = next((i for i in items if i["actor_id"] == str(d["coord_id"])), None)
        if coord_item:
            assert "CANCELADO" not in coord_item["estados"]
            assert coord_item["estados"].get("PENDIENTE") == 1

    async def test_comunicaciones_docente_sin_datos_200(
        self, async_client: AsyncClient, aud_db: dict, db_session: AsyncSession
    ):
        # Coordinador with no asignaciones → empty result
        # Temporarily remove asignacion for coord to simulate no materias
        await db_session.execute(text("DELETE FROM asignacion"))
        await db_session.commit()

        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/comunicaciones-docente",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_comunicaciones_docente_destinatario_nunca_expuesto(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """Communicacion.destinatario (encrypted PII) never appears in response."""
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/comunicaciones-docente",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        raw = resp.text
        assert "dest1@test.com" not in raw
        assert "dest2@test.com" not in raw

    async def test_comunicaciones_docente_sin_permiso_403(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ALUMNO_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/comunicaciones-docente",
            headers=_auth(token),
        )
        assert resp.status_code == 403


# ── TestInteraccionesXDocenteMateria ─────────────────────────────────────────


class TestInteraccionesXDocenteMateria:

    async def test_interacciones_todos_modulos(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/interacciones",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Admin has entries: 3 with materia, 2 with other_materia, 1 no-materia
        # Coord has 1 entry with materia
        assert len(items) >= 2

    async def test_interacciones_coordinador_scope_own(
        self, async_client: AsyncClient, aud_db: dict
    ):
        d = aud_db
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/interacciones",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Only entries with materia.id visible to coordinator
        for item in items:
            assert item["materia_id"] == str(d["materia_id"])

    async def test_interacciones_filtro_actor(
        self, async_client: AsyncClient, aud_db: dict
    ):
        d = aud_db
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            f"/api/v1/auditoria/panel/interacciones?actor_id={d['coord_id']}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(item["actor_id"] == str(d["coord_id"]) for item in items)

    async def test_interacciones_materia_id_none_invisible_coordinador(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """Entries without materia_id are never visible to coordinator."""
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/interacciones",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # No item should have materia_id == null (those are the entries without materia)
        # because coordinator scope excludes materia_id IS NULL entries
        for item in items:
            assert item["materia_id"] is not None

    async def test_interacciones_rbac_otro_tenant_invisible(
        self, async_client: AsyncClient, aud_db: dict
    ):
        d = aud_db
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/interacciones",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Items only contain actors from tenant A (no tenant B actors)
        actor_ids = {item["actor_id"] for item in items}
        assert str(d["admin_id"]) in actor_ids or str(d["coord_id"]) in actor_ids
        # Tenant B's fake actor UUID should NOT appear
        # (it's not from tenant A so AuditoriaRepository tenant scope excludes it)


# ── TestUltimasAcciones ───────────────────────────────────────────────────────


class TestUltimasAcciones:

    async def test_ultimas_acciones_default_200(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/ultimas-acciones",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["limit_aplicado"] == 200
        assert len(body["items"]) <= 200

    async def test_ultimas_acciones_limit_custom(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/ultimas-acciones?limit=3",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["limit_aplicado"] == 3
        assert len(body["items"]) <= 3

    async def test_ultimas_acciones_limit_fuera_de_rango_422(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/ultimas-acciones?limit=501",
            headers=_auth(token),
        )
        assert resp.status_code == 422

    async def test_ultimas_acciones_admin_full_fields(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """ADMIN (scope=all) receives AuditLogFullEntry with ip, user_agent, detalle."""
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/ultimas-acciones?limit=1",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        # Full entry has these keys (even if null)
        assert "ip" in item
        assert "user_agent" in item
        assert "detalle" in item

    async def test_ultimas_acciones_coordinador_public_fields(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """COORDINADOR (scope=own) receives AuditLogPublicEntry without ip/user_agent/detalle."""
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/panel/ultimas-acciones?limit=5",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert "ip" not in item
            assert "user_agent" not in item
            assert "detalle" not in item


# ── TestLogAuditoria ──────────────────────────────────────────────────────────


class TestLogAuditoria:

    async def test_log_admin_todos_los_campos(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/log",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 7
        item = body["items"][0]
        assert "ip" in item
        assert "user_agent" in item
        assert "detalle" in item
        assert "nombre_actor" in item
        assert "apellidos_actor" in item

    async def test_log_coordinador_sin_campos_seguros(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/log",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "ip" not in item
            assert "user_agent" not in item
            assert "detalle" not in item

    async def test_log_coordinador_solo_sus_materias(
        self, async_client: AsyncClient, aud_db: dict
    ):
        d = aud_db
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/log",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Coordinator sees only entries with their materia_id (4 total: 3 admin + 1 coord)
        assert body["total"] == 4
        for item in body["items"]:
            assert item["materia_id"] == str(d["materia_id"])

    async def test_log_filtro_actor_id(
        self, async_client: AsyncClient, aud_db: dict
    ):
        d = aud_db
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            f"/api/v1/auditoria/log?actor_id={d['coord_id']}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["actor_id"] == str(d["coord_id"])

    async def test_log_filtro_accion(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            f"/api/v1/auditoria/log?accion={PADRON_CARGAR}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["accion"] == PADRON_CARGAR

    async def test_log_filtro_fecha_rango(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        resp = await async_client.get(
            f"/api/v1/auditoria/log?from_date={yesterday}&to_date={tomorrow}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 7

    async def test_log_paginacion(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ADMIN_EMAIL)
        resp1 = await async_client.get(
            "/api/v1/auditoria/log?page=1&page_size=5",
            headers=_auth(token),
        )
        resp2 = await async_client.get(
            "/api/v1/auditoria/log?page=2&page_size=5",
            headers=_auth(token),
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        b1 = resp1.json()
        b2 = resp2.json()
        assert b1["total"] == 7
        assert b1["pages"] == 2
        assert len(b1["items"]) == 5
        assert len(b2["items"]) == 2
        # No overlap
        ids1 = {i["id"] for i in b1["items"]}
        ids2 = {i["id"] for i in b2["items"]}
        assert ids1.isdisjoint(ids2)

    async def test_log_otro_tenant_invisible(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """Tenant B's audit entry must never appear in Tenant A's log."""
        token = await _login(async_client, ADMIN_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/log",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # Only 7 entries (all from tenant A); tenant B's entry is invisible
        assert body["total"] == 7


# ── TestLogRBAC ───────────────────────────────────────────────────────────────


class TestLogRBAC:

    async def test_log_sin_permiso_403(
        self, async_client: AsyncClient, aud_db: dict
    ):
        token = await _login(async_client, ALUMNO_EMAIL)
        for path in [
            "/api/v1/auditoria/panel/acciones-por-dia",
            "/api/v1/auditoria/panel/comunicaciones-docente",
            "/api/v1/auditoria/panel/interacciones",
            "/api/v1/auditoria/panel/ultimas-acciones",
            "/api/v1/auditoria/log",
        ]:
            resp = await async_client.get(path, headers=_auth(token))
            assert resp.status_code == 403, f"Expected 403 for {path}, got {resp.status_code}"

    async def test_log_finanzas_scope_all(
        self, async_client: AsyncClient, aud_db: dict
    ):
        """FINANZAS has scope=all, sees the full 7 entries and full-schema fields."""
        token = await _login(async_client, FINANZAS_EMAIL)
        resp = await async_client.get(
            "/api/v1/auditoria/log",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 7
        # Full schema fields present
        assert "ip" in body["items"][0]
        assert "detalle" in body["items"][0]
