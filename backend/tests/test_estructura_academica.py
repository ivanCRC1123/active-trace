"""C-06 estructura-academica — integration tests.

Covers:
- ABM completo de Carrera, Cohorte y Materia (CRUD + soft-delete)
- Unicidad por tenant (409 en duplicados, OK en otro tenant)
- Aislamiento multi-tenant (404 cross-tenant)
- Regla de negocio: Carrera inactiva bloquea creación de Cohorte
- RBAC: PROFESOR (sin permiso) recibe 403
- Estado: Inactiva no equivale a soft-deleted
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_CODE = "estructura-test"
OTHER_TENANT_CODE = "estructura-test-b"
USER_PASS = "Admin123!"
ADMIN_EMAIL = "est.admin@test.edu.ar"
PROFESOR_EMAIL = "est.prof@test.edu.ar"
ADMIN_B_EMAIL = "est.admin.b@test.edu.ar"


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def struct_db(db_session: AsyncSession) -> dict:
    """Seed two tenants with one ADMIN each plus a PROFESOR in tenant A."""
    # Clean slate (reverse FK order)
    # audit_log has FK actor_id → user (RESTRICT) — truncate before deleting users
    await db_session.execute(text("TRUNCATE TABLE audit_log"))
    await db_session.execute(text("DELETE FROM cohorte"))
    await db_session.execute(text("DELETE FROM materia"))
    await db_session.execute(text("DELETE FROM carrera"))
    await db_session.execute(text("DELETE FROM user_rol"))
    await db_session.execute(text("DELETE FROM rol_permiso"))
    await db_session.execute(text("DELETE FROM permiso"))
    await db_session.execute(text("DELETE FROM rol"))
    await db_session.execute(text("DELETE FROM refresh_token"))
    await db_session.execute(text("DELETE FROM recovery_token"))
    await db_session.execute(text('DELETE FROM "user"'))
    await db_session.execute(text("DELETE FROM tenant"))
    await db_session.commit()

    def _user(email: str, tid) -> User:
        return User(
            email=email,
            password_hash=hash_password(USER_PASS),
            nombre="Test",
            apellido="User",
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
        )

    # Tenant A
    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Estructura Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    admin_a = _user(ADMIN_EMAIL, tid_a)
    profesor = _user(PROFESOR_EMAIL, tid_a)
    db_session.add_all([admin_a, profesor])
    await db_session.flush()
    await db_session.refresh(admin_a)
    await db_session.refresh(profesor)

    rol_admin_a = Rol(tenant_id=tid_a, nombre="ADMIN", descripcion="Admin")
    rol_prof = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    db_session.add_all([rol_admin_a, rol_prof])
    await db_session.flush()
    await db_session.refresh(rol_admin_a)

    p_est = Permiso(
        tenant_id=tid_a,
        codigo="estructura_academica:gestionar",
        modulo="estructura_academica",
        descripcion="Gestionar estructura",
    )
    p_com = Permiso(
        tenant_id=tid_a,
        codigo="comunicacion:confirmar_aviso",
        modulo="comunicacion",
        descripcion="Confirmar aviso",
    )
    db_session.add_all([p_est, p_com])
    await db_session.flush()
    await db_session.refresh(p_est)
    await db_session.refresh(p_com)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_est.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_com.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=admin_a.id, rol_id=rol_admin_a.id),
        # profesor has no estructura permission (no UserRol link to any role with that perm)
    ])
    await db_session.flush()

    # Tenant B — independent admin
    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Estructura Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    admin_b = _user(ADMIN_B_EMAIL, tid_b)
    db_session.add(admin_b)
    await db_session.flush()
    await db_session.refresh(admin_b)

    rol_admin_b = Rol(tenant_id=tid_b, nombre="ADMIN", descripcion="Admin")
    db_session.add(rol_admin_b)
    await db_session.flush()
    await db_session.refresh(rol_admin_b)

    p_est_b = Permiso(
        tenant_id=tid_b,
        codigo="estructura_academica:gestionar",
        modulo="estructura_academica",
        descripcion="Gestionar estructura",
    )
    db_session.add(p_est_b)
    await db_session.flush()
    await db_session.refresh(p_est_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_admin_b.id, permiso_id=p_est_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=admin_b.id, rol_id=rol_admin_b.id),
    ])
    await db_session.flush()
    await db_session.commit()

    return {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "admin_a_id": admin_a.id,
        "admin_b_id": admin_b.id,
        "profesor_id": profesor.id,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# ── TestCarreraABM ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCarreraABM:
    async def test_create_carrera_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/admin/carreras",
            json={"codigo": "TUPAD", "nombre": "Tecnicatura UP"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["codigo"] == "TUPAD"
        assert body["nombre"] == "Tecnicatura UP"
        assert body["estado"] == "Activa"
        assert "id" in body
        assert "tenant_id" in body

    async def test_create_carrera_codigo_duplicado_returns_409(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        await async_client.post("/api/v1/admin/carreras", json={"codigo": "DUP", "nombre": "A"}, headers=headers)
        resp = await async_client.post("/api/v1/admin/carreras", json={"codigo": "DUP", "nombre": "B"}, headers=headers)
        assert resp.status_code == 409

    async def test_create_carrera_codigo_duplicado_otro_tenant_ok(self, async_client, struct_db):
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        resp_a = await async_client.post(
            "/api/v1/admin/carreras", json={"codigo": "SHARED", "nombre": "A"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        resp_b = await async_client.post(
            "/api/v1/admin/carreras", json={"codigo": "SHARED", "nombre": "B"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp_a.status_code == 201
        assert resp_b.status_code == 201

    async def test_list_carreras_solo_propio_tenant(self, async_client, struct_db):
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        await async_client.post("/api/v1/admin/carreras", json={"codigo": "ONLY_A", "nombre": "A"}, headers={"Authorization": f"Bearer {token_a}"})
        await async_client.post("/api/v1/admin/carreras", json={"codigo": "ONLY_B", "nombre": "B"}, headers={"Authorization": f"Bearer {token_b}"})
        resp = await async_client.get("/api/v1/admin/carreras", headers={"Authorization": f"Bearer {token_a}"})
        assert resp.status_code == 200
        codigos = [c["codigo"] for c in resp.json()]
        assert "ONLY_A" in codigos
        assert "ONLY_B" not in codigos

    async def test_get_carrera_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = (await async_client.post("/api/v1/admin/carreras", json={"codigo": "GET_TEST", "nombre": "T"}, headers=headers)).json()
        resp = await async_client.get(f"/api/v1/admin/carreras/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["codigo"] == "GET_TEST"

    async def test_get_carrera_otro_tenant_returns_404(self, async_client, struct_db):
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        created = (await async_client.post("/api/v1/admin/carreras", json={"codigo": "A_ONLY", "nombre": "A"}, headers={"Authorization": f"Bearer {token_a}"})).json()
        resp = await async_client.get(f"/api/v1/admin/carreras/{created['id']}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code == 404

    async def test_update_carrera_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = (await async_client.post("/api/v1/admin/carreras", json={"codigo": "UPD", "nombre": "Orig"}, headers=headers)).json()
        resp = await async_client.patch(f"/api/v1/admin/carreras/{created['id']}", json={"nombre": "Updated"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["nombre"] == "Updated"

    async def test_soft_delete_carrera_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = (await async_client.post("/api/v1/admin/carreras", json={"codigo": "DEL", "nombre": "D"}, headers=headers)).json()
        del_resp = await async_client.delete(f"/api/v1/admin/carreras/{created['id']}", headers=headers)
        assert del_resp.status_code == 204
        get_resp = await async_client.get(f"/api/v1/admin/carreras/{created['id']}", headers=headers)
        assert get_resp.status_code == 404

    async def test_no_admin_returns_403(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, PROFESOR_EMAIL)
        resp = await async_client.post(
            "/api/v1/admin/carreras",
            json={"codigo": "NOADMIN", "nombre": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# ── TestCohorteABM ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCohorteABM:
    async def _carrera_activa(self, client, token) -> str:
        resp = await client.post(
            "/api/v1/admin/carreras",
            json={"codigo": f"C{uuid.uuid4().hex[:4]}", "nombre": "Carrera"},
            headers={"Authorization": f"Bearer {token}"},
        )
        return resp.json()["id"]

    async def test_create_cohorte_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        carrera_id = await self._carrera_activa(async_client, token)
        resp = await async_client.post(
            "/api/v1/admin/cohortes",
            json={"carrera_id": carrera_id, "nombre": "AGO-2025", "anio": 2025, "vig_desde": "2025-08-01"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["nombre"] == "AGO-2025"
        assert body["anio"] == 2025
        assert body["vig_hasta"] is None
        assert body["estado"] == "Activa"

    async def test_create_cohorte_carrera_inactiva_returns_400(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera_id = await self._carrera_activa(async_client, token)
        await async_client.patch(f"/api/v1/admin/carreras/{carrera_id}", json={"estado": "Inactiva"}, headers=headers)
        resp = await async_client.post(
            "/api/v1/admin/cohortes",
            json={"carrera_id": carrera_id, "nombre": "MAR-2026", "anio": 2026, "vig_desde": "2026-03-01"},
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_create_cohorte_carrera_otro_tenant_returns_404(self, async_client, struct_db):
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        carrera_a_id = await self._carrera_activa(async_client, token_a)
        resp = await async_client.post(
            "/api/v1/admin/cohortes",
            json={"carrera_id": carrera_a_id, "nombre": "X", "anio": 2025, "vig_desde": "2025-01-01"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404

    async def test_create_cohorte_nombre_duplicado_returns_409(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera_id = await self._carrera_activa(async_client, token)
        payload = {"carrera_id": carrera_id, "nombre": "AGO-2025", "anio": 2025, "vig_desde": "2025-08-01"}
        await async_client.post("/api/v1/admin/cohortes", json=payload, headers=headers)
        resp = await async_client.post("/api/v1/admin/cohortes", json=payload, headers=headers)
        assert resp.status_code == 409

    async def test_list_cohortes_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera_id = await self._carrera_activa(async_client, token)
        await async_client.post("/api/v1/admin/cohortes", json={"carrera_id": carrera_id, "nombre": "COH1", "anio": 2025, "vig_desde": "2025-01-01"}, headers=headers)
        resp = await async_client.get("/api/v1/admin/cohortes", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_update_cohorte_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera_id = await self._carrera_activa(async_client, token)
        created = (await async_client.post("/api/v1/admin/cohortes", json={"carrera_id": carrera_id, "nombre": "UCOH", "anio": 2025, "vig_desde": "2025-01-01"}, headers=headers)).json()
        resp = await async_client.patch(f"/api/v1/admin/cohortes/{created['id']}", json={"vig_hasta": "2025-12-31"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["vig_hasta"] == "2025-12-31"

    async def test_soft_delete_cohorte_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera_id = await self._carrera_activa(async_client, token)
        created = (await async_client.post("/api/v1/admin/cohortes", json={"carrera_id": carrera_id, "nombre": "DCOH", "anio": 2025, "vig_desde": "2025-01-01"}, headers=headers)).json()
        del_resp = await async_client.delete(f"/api/v1/admin/cohortes/{created['id']}", headers=headers)
        assert del_resp.status_code == 204
        assert (await async_client.get(f"/api/v1/admin/cohortes/{created['id']}", headers=headers)).status_code == 404

    async def test_no_admin_returns_403(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, PROFESOR_EMAIL)
        resp = await async_client.get("/api/v1/admin/cohortes", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# ── TestMateriaABM ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMateriaABM:
    async def test_create_materia_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/admin/materias",
            json={"codigo": "PROG_I", "nombre": "Programación I"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["codigo"] == "PROG_I"
        assert body["estado"] == "Activa"

    async def test_create_materia_codigo_duplicado_returns_409(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        await async_client.post("/api/v1/admin/materias", json={"codigo": "DUP_M", "nombre": "A"}, headers=headers)
        resp = await async_client.post("/api/v1/admin/materias", json={"codigo": "DUP_M", "nombre": "B"}, headers=headers)
        assert resp.status_code == 409

    async def test_create_materia_codigo_duplicado_otro_tenant_ok(self, async_client, struct_db):
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        resp_a = await async_client.post("/api/v1/admin/materias", json={"codigo": "SHARED_M", "nombre": "A"}, headers={"Authorization": f"Bearer {token_a}"})
        resp_b = await async_client.post("/api/v1/admin/materias", json={"codigo": "SHARED_M", "nombre": "B"}, headers={"Authorization": f"Bearer {token_b}"})
        assert resp_a.status_code == 201
        assert resp_b.status_code == 201

    async def test_list_materias_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        await async_client.post("/api/v1/admin/materias", json={"codigo": "LIST_M", "nombre": "L"}, headers=headers)
        resp = await async_client.get("/api/v1/admin/materias", headers=headers)
        assert resp.status_code == 200
        assert any(m["codigo"] == "LIST_M" for m in resp.json())

    async def test_get_materia_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = (await async_client.post("/api/v1/admin/materias", json={"codigo": "GET_M", "nombre": "G"}, headers=headers)).json()
        resp = await async_client.get(f"/api/v1/admin/materias/{created['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["codigo"] == "GET_M"

    async def test_update_materia_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = (await async_client.post("/api/v1/admin/materias", json={"codigo": "UPD_M", "nombre": "Orig"}, headers=headers)).json()
        resp = await async_client.patch(f"/api/v1/admin/materias/{created['id']}", json={"nombre": "Updated"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["nombre"] == "Updated"

    async def test_soft_delete_materia_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = (await async_client.post("/api/v1/admin/materias", json={"codigo": "DEL_M", "nombre": "D"}, headers=headers)).json()
        del_resp = await async_client.delete(f"/api/v1/admin/materias/{created['id']}", headers=headers)
        assert del_resp.status_code == 204
        assert (await async_client.get(f"/api/v1/admin/materias/{created['id']}", headers=headers)).status_code == 404

    async def test_no_admin_returns_403(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, PROFESOR_EMAIL)
        resp = await async_client.get("/api/v1/admin/materias", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# ── TestEstadoYVigencia ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestEstadoYVigencia:
    async def test_carrera_inactiva_bloquea_cohorte(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera = (await async_client.post("/api/v1/admin/carreras", json={"codigo": f"BLK{uuid.uuid4().hex[:4]}", "nombre": "X"}, headers=headers)).json()
        await async_client.patch(f"/api/v1/admin/carreras/{carrera['id']}", json={"estado": "Inactiva"}, headers=headers)
        resp = await async_client.post(
            "/api/v1/admin/cohortes",
            json={"carrera_id": carrera["id"], "nombre": "COH", "anio": 2025, "vig_desde": "2025-01-01"},
            headers=headers,
        )
        assert resp.status_code == 400

    async def test_reactivar_carrera_permite_cohorte(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera = (await async_client.post("/api/v1/admin/carreras", json={"codigo": f"REACT{uuid.uuid4().hex[:4]}", "nombre": "X"}, headers=headers)).json()
        await async_client.patch(f"/api/v1/admin/carreras/{carrera['id']}", json={"estado": "Inactiva"}, headers=headers)
        await async_client.patch(f"/api/v1/admin/carreras/{carrera['id']}", json={"estado": "Activa"}, headers=headers)
        resp = await async_client.post(
            "/api/v1/admin/cohortes",
            json={"carrera_id": carrera["id"], "nombre": "COH", "anio": 2025, "vig_desde": "2025-01-01"},
            headers=headers,
        )
        assert resp.status_code == 201

    async def test_materia_inactiva_aparece_en_list(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = (await async_client.post("/api/v1/admin/materias", json={"codigo": "INACT_M", "nombre": "M"}, headers=headers)).json()
        await async_client.patch(f"/api/v1/admin/materias/{created['id']}", json={"estado": "Inactiva"}, headers=headers)
        resp = await async_client.get("/api/v1/admin/materias", headers=headers)
        assert resp.status_code == 200
        estados = {m["codigo"]: m["estado"] for m in resp.json()}
        assert estados.get("INACT_M") == "Inactiva"

    async def test_cohorte_sin_vig_hasta_abierta_ok(self, async_client, struct_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        carrera = (await async_client.post("/api/v1/admin/carreras", json={"codigo": f"OPEN{uuid.uuid4().hex[:4]}", "nombre": "X"}, headers=headers)).json()
        resp = await async_client.post(
            "/api/v1/admin/cohortes",
            json={"carrera_id": carrera["id"], "nombre": "OPEN-COH", "anio": 2025, "vig_desde": "2025-01-01"},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["vig_hasta"] is None
