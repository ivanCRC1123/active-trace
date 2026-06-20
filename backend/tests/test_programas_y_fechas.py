"""C-17 programas-y-fechas-academicas — integration tests.

Covers:
- ProgramaMateria ABM (CRUD, unicidad, aislamiento tenant, referencia opaca)
- FechaAcademica ABM (CRUD, unicidad, aislamiento tenant)
- Fragmento LMS (contenido, vacío, filtro por periodo, orden canónico)
- RBAC: ADMIN + COORDINADOR → acceso; PROFESOR → 403
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_CODE = "prog-test-a"
OTHER_TENANT_CODE = "prog-test-b"
USER_PASS = "Admin123!"
ADMIN_EMAIL = "prog.admin@test.edu.ar"
COORD_EMAIL = "prog.coord@test.edu.ar"
PROF_EMAIL = "prog.prof@test.edu.ar"
ADMIN_B_EMAIL = "prog.admin.b@test.edu.ar"


# ── Fixture ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def prog_db(db_session: AsyncSession) -> dict:
    """Seed two tenants with users, roles, permissions, and academic structure."""
    # Clean C-17 tables first (RESTRICT FKs, so order matters)
    await db_session.execute(text("DELETE FROM fecha_academica"))
    await db_session.execute(text("DELETE FROM programa_materia"))
    await db_session.execute(text("DELETE FROM asignacion"))
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
            email_cifrado=encrypt(email),
            email_hash=hmac_email(email),
            password_hash=hash_password(USER_PASS),
            nombre="Test",
            apellidos="User",
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
        )

    # ── Tenant A ──────────────────────────────────────────────────────────────

    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Programas Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    admin_a = _user(ADMIN_EMAIL, tid_a)
    coord_a = _user(COORD_EMAIL, tid_a)
    prof_a = _user(PROF_EMAIL, tid_a)
    db_session.add_all([admin_a, coord_a, prof_a])
    await db_session.flush()
    await db_session.refresh(admin_a)
    await db_session.refresh(coord_a)
    await db_session.refresh(prof_a)

    rol_admin_a = Rol(tenant_id=tid_a, nombre="ADMIN", descripcion="Admin")
    rol_coord_a = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    rol_prof_a = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    db_session.add_all([rol_admin_a, rol_coord_a, rol_prof_a])
    await db_session.flush()
    await db_session.refresh(rol_admin_a)
    await db_session.refresh(rol_coord_a)

    p_prog = Permiso(
        tenant_id=tid_a, codigo="programas:gestionar",
        modulo="programas", descripcion="Gestionar programas",
    )
    p_fechas = Permiso(
        tenant_id=tid_a, codigo="fechas_academicas:gestionar",
        modulo="fechas_academicas", descripcion="Gestionar fechas",
    )
    db_session.add_all([p_prog, p_fechas])
    await db_session.flush()
    await db_session.refresh(p_prog)
    await db_session.refresh(p_fechas)

    db_session.add_all([
        # ADMIN gets both permissions
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_prog.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_fechas.id, scope="all"),
        # COORDINADOR gets both permissions
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord_a.id, permiso_id=p_prog.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord_a.id, permiso_id=p_fechas.id, scope="all"),
        # User-role assignments
        UserRol(tenant_id=tid_a, user_id=admin_a.id, rol_id=rol_admin_a.id),
        UserRol(tenant_id=tid_a, user_id=coord_a.id, rol_id=rol_coord_a.id),
        # PROFESOR gets no programas/fechas permissions
        UserRol(tenant_id=tid_a, user_id=prof_a.id, rol_id=rol_prof_a.id),
    ])
    await db_session.flush()

    # Academic structure for tenant A
    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-A", nombre="Ingeniería A")
    materia_a = Materia(tenant_id=tid_a, codigo="PROG_I", nombre="Programación I")
    db_session.add_all([carrera_a, materia_a])
    await db_session.flush()
    await db_session.refresh(carrera_a)
    await db_session.refresh(materia_a)

    cohorte_a = Cohorte(
        tenant_id=tid_a, carrera_id=carrera_a.id,
        nombre="MAR-2026", anio=2026,
        vig_desde=date(2026, 3, 1),
    )
    db_session.add(cohorte_a)
    await db_session.flush()
    await db_session.refresh(cohorte_a)

    # ── Tenant B ──────────────────────────────────────────────────────────────

    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Programas Test B")
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

    p_prog_b = Permiso(
        tenant_id=tid_b, codigo="programas:gestionar",
        modulo="programas", descripcion="Gestionar programas",
    )
    p_fechas_b = Permiso(
        tenant_id=tid_b, codigo="fechas_academicas:gestionar",
        modulo="fechas_academicas", descripcion="Gestionar fechas",
    )
    db_session.add_all([p_prog_b, p_fechas_b])
    await db_session.flush()
    await db_session.refresh(p_prog_b)
    await db_session.refresh(p_fechas_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_admin_b.id, permiso_id=p_prog_b.id, scope="all"),
        RolPermiso(tenant_id=tid_b, rol_id=rol_admin_b.id, permiso_id=p_fechas_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=admin_b.id, rol_id=rol_admin_b.id),
    ])
    await db_session.flush()

    carrera_b = Carrera(tenant_id=tid_b, codigo="ING-B", nombre="Ingeniería B")
    materia_b = Materia(tenant_id=tid_b, codigo="PROG_I", nombre="Programación I")
    db_session.add_all([carrera_b, materia_b])
    await db_session.flush()
    await db_session.refresh(carrera_b)
    await db_session.refresh(materia_b)

    cohorte_b = Cohorte(
        tenant_id=tid_b, carrera_id=carrera_b.id,
        nombre="MAR-2026", anio=2026,
        vig_desde=date(2026, 3, 1),
    )
    db_session.add(cohorte_b)
    await db_session.flush()
    await db_session.refresh(cohorte_b)

    await db_session.commit()

    return {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "admin_a_id": admin_a.id,
        "coord_a_id": coord_a.id,
        "prof_a_id": prof_a.id,
        "admin_b_id": admin_b.id,
        "carrera_a_id": carrera_a.id,
        "cohorte_a_id": cohorte_a.id,
        "materia_a_id": materia_a.id,
        "carrera_b_id": carrera_b.id,
        "cohorte_b_id": cohorte_b.id,
        "materia_b_id": materia_b.id,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── TestProgramaMateriaABM ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestProgramaMateriaABM:
    async def test_create_programa_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/programas/",
            headers=_auth(token),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Programa 2026",
                "referencia_archivo": "s3://bucket/prog_2026.pdf",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["titulo"] == "Programa 2026"
        assert body["referencia_archivo"] == "s3://bucket/prog_2026.pdf"
        assert body["tenant_id"] == str(d["tenant_a_id"])
        assert "cargado_at" in body

    async def test_create_programa_materia_otro_tenant_returns_404(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/programas/",
            headers=_auth(token),
            json={
                "materia_id": str(d["materia_b_id"]),  # tenant B's materia
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Programa",
                "referencia_archivo": "s3://prog.pdf",
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_create_programa_carrera_otro_tenant_returns_404(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/programas/",
            headers=_auth(token),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_b_id"]),  # tenant B's carrera
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Programa",
                "referencia_archivo": "s3://prog.pdf",
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_create_programa_cohorte_otro_tenant_returns_404(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/programas/",
            headers=_auth(token),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_b_id"]),  # tenant B's cohorte
                "titulo": "Programa",
                "referencia_archivo": "s3://prog.pdf",
            },
        )
        assert resp.status_code == 404, resp.text

    async def test_create_programa_duplicado_returns_409(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        payload = {
            "materia_id": str(d["materia_a_id"]),
            "carrera_id": str(d["carrera_a_id"]),
            "cohorte_id": str(d["cohorte_a_id"]),
            "titulo": "Programa",
            "referencia_archivo": "s3://prog.pdf",
        }
        r1 = await async_client.post("/api/v1/programas/", headers=_auth(token), json=payload)
        assert r1.status_code == 201
        r2 = await async_client.post("/api/v1/programas/", headers=_auth(token), json=payload)
        assert r2.status_code == 409

    async def test_list_programas_filtra_por_tenant(self, async_client, prog_db):
        d = prog_db
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        # Create one in tenant A
        await async_client.post(
            "/api/v1/programas/", headers=_auth(token_a),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Prog A", "referencia_archivo": "s3://a.pdf",
            },
        )
        # Create one in tenant B
        await async_client.post(
            "/api/v1/programas/", headers=_auth(token_b),
            json={
                "materia_id": str(d["materia_b_id"]),
                "carrera_id": str(d["carrera_b_id"]),
                "cohorte_id": str(d["cohorte_b_id"]),
                "titulo": "Prog B", "referencia_archivo": "s3://b.pdf",
            },
        )
        list_a = await async_client.get("/api/v1/programas/", headers=_auth(token_a))
        assert list_a.status_code == 200
        items = list_a.json()
        assert len(items) == 1
        assert items[0]["titulo"] == "Prog A"

    async def test_get_programa_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        cr = await async_client.post(
            "/api/v1/programas/", headers=_auth(token),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Prog GET", "referencia_archivo": "s3://get.pdf",
            },
        )
        prog_id = cr.json()["id"]
        resp = await async_client.get(f"/api/v1/programas/{prog_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["titulo"] == "Prog GET"

    async def test_get_programa_otro_tenant_returns_404(self, async_client, prog_db):
        d = prog_db
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        cr = await async_client.post(
            "/api/v1/programas/", headers=_auth(token_a),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Prog", "referencia_archivo": "s3://x.pdf",
            },
        )
        prog_id = cr.json()["id"]
        resp = await async_client.get(f"/api/v1/programas/{prog_id}", headers=_auth(token_b))
        assert resp.status_code == 404

    async def test_update_programa_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        cr = await async_client.post(
            "/api/v1/programas/", headers=_auth(token),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Orig", "referencia_archivo": "s3://orig.pdf",
            },
        )
        prog_id = cr.json()["id"]
        original_cargado_at = cr.json()["cargado_at"]

        resp = await async_client.patch(
            f"/api/v1/programas/{prog_id}", headers=_auth(token),
            json={"titulo": "Updated", "referencia_archivo": "s3://new.pdf"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["titulo"] == "Updated"
        assert body["referencia_archivo"] == "s3://new.pdf"
        # cargado_at must not change on PATCH
        assert body["cargado_at"] == original_cargado_at

    async def test_soft_delete_programa_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        cr = await async_client.post(
            "/api/v1/programas/", headers=_auth(token),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Del", "referencia_archivo": "s3://del.pdf",
            },
        )
        prog_id = cr.json()["id"]
        del_resp = await async_client.delete(f"/api/v1/programas/{prog_id}", headers=_auth(token))
        assert del_resp.status_code == 204
        # GET after delete → 404
        get_resp = await async_client.get(f"/api/v1/programas/{prog_id}", headers=_auth(token))
        assert get_resp.status_code == 404

    async def test_profesor_programas_returns_403(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.get("/api/v1/programas/", headers=_auth(token))
        assert resp.status_code == 403

    async def test_coordinador_puede_crear_programa(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/programas/", headers=_auth(token),
            json={
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a_id"]),
                "titulo": "Prog Coord", "referencia_archivo": "s3://coord.pdf",
            },
        )
        assert resp.status_code == 201, resp.text


# ── TestFechaAcademicaABM ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFechaAcademicaABM:
    def _fecha_payload(self, d: dict, **overrides) -> dict:
        base = {
            "materia_id": str(d["materia_a_id"]),
            "cohorte_id": str(d["cohorte_a_id"]),
            "tipo": "Parcial",
            "numero": 1,
            "periodo": "2026-1",
            "fecha": "2026-04-15",
            "titulo": "1er Parcial",
        }
        base.update(overrides)
        return base

    async def test_create_fecha_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/fechas-academicas/",
            headers=_auth(token),
            json=self._fecha_payload(d),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["tipo"] == "Parcial"
        assert body["numero"] == 1
        assert body["periodo"] == "2026-1"
        assert body["tenant_id"] == str(d["tenant_a_id"])

    async def test_create_fecha_materia_otro_tenant_returns_404(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/fechas-academicas/",
            headers=_auth(token),
            json=self._fecha_payload(d, materia_id=str(d["materia_b_id"])),
        )
        assert resp.status_code == 404

    async def test_create_fecha_cohorte_otro_tenant_returns_404(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/fechas-academicas/",
            headers=_auth(token),
            json=self._fecha_payload(d, cohorte_id=str(d["cohorte_b_id"])),
        )
        assert resp.status_code == 404

    async def test_create_fecha_duplicada_returns_409(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        payload = self._fecha_payload(d)
        r1 = await async_client.post("/api/v1/fechas-academicas/", headers=_auth(token), json=payload)
        assert r1.status_code == 201
        r2 = await async_client.post("/api/v1/fechas-academicas/", headers=_auth(token), json=payload)
        assert r2.status_code == 409

    async def test_create_fecha_mismo_tenant_otro_tipo_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        r1 = await async_client.post(
            "/api/v1/fechas-academicas/", headers=_auth(token),
            json=self._fecha_payload(d, tipo="Parcial", numero=1, periodo="2026-1"),
        )
        assert r1.status_code == 201
        r2 = await async_client.post(
            "/api/v1/fechas-academicas/", headers=_auth(token),
            json=self._fecha_payload(d, tipo="TP", numero=1, periodo="2026-1"),
        )
        assert r2.status_code == 201

    async def test_numero_invalido_returns_422(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/fechas-academicas/",
            headers=_auth(token),
            json=self._fecha_payload(d, numero=0),
        )
        assert resp.status_code == 422

    async def test_list_fechas_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        await async_client.post(
            "/api/v1/fechas-academicas/", headers=_auth(token),
            json=self._fecha_payload(d, tipo="Parcial", numero=1),
        )
        await async_client.post(
            "/api/v1/fechas-academicas/", headers=_auth(token),
            json=self._fecha_payload(d, tipo="Parcial", numero=2, fecha="2026-05-20"),
        )
        resp = await async_client.get("/api/v1/fechas-academicas/", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_update_fecha_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        cr = await async_client.post(
            "/api/v1/fechas-academicas/", headers=_auth(token),
            json=self._fecha_payload(d),
        )
        fecha_id = cr.json()["id"]
        resp = await async_client.patch(
            f"/api/v1/fechas-academicas/{fecha_id}", headers=_auth(token),
            json={"fecha": "2026-04-22", "titulo": "1er Parcial (reprogramado)"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["fecha"] == "2026-04-22"
        assert body["titulo"] == "1er Parcial (reprogramado)"
        # tipo/numero/periodo must not change
        assert body["tipo"] == "Parcial"
        assert body["numero"] == 1
        assert body["periodo"] == "2026-1"

    async def test_soft_delete_fecha_ok(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        cr = await async_client.post(
            "/api/v1/fechas-academicas/", headers=_auth(token),
            json=self._fecha_payload(d),
        )
        fecha_id = cr.json()["id"]
        del_resp = await async_client.delete(
            f"/api/v1/fechas-academicas/{fecha_id}", headers=_auth(token)
        )
        assert del_resp.status_code == 204
        get_resp = await async_client.get(
            f"/api/v1/fechas-academicas/{fecha_id}", headers=_auth(token)
        )
        assert get_resp.status_code == 404

    async def test_profesor_fechas_returns_403(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.get("/api/v1/fechas-academicas/", headers=_auth(token))
        assert resp.status_code == 403

    async def test_coordinador_puede_gestionar_fechas(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        d = prog_db
        resp = await async_client.post(
            "/api/v1/fechas-academicas/", headers=_auth(token),
            json=self._fecha_payload(d, titulo="Fecha Coord"),
        )
        assert resp.status_code == 201, resp.text


# ── TestFragmentoLMS ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFragmentoLMS:
    async def _create_fecha(self, client, token, d, **kwargs):
        payload = {
            "materia_id": str(d["materia_a_id"]),
            "cohorte_id": str(d["cohorte_a_id"]),
            "periodo": "2026-1",
            "fecha": "2026-04-15",
            "titulo": "Fecha",
            **kwargs,
        }
        resp = await client.post("/api/v1/fechas-academicas/", headers=_auth(token), json=payload)
        assert resp.status_code == 201, resp.text

    async def test_fragmento_lms_sin_fechas_devuelve_vacio(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        resp = await async_client.get(
            "/api/v1/fechas-academicas/fragmento-lms",
            headers=_auth(token),
            params={"materia_id": str(d["materia_a_id"]), "cohorte_id": str(d["cohorte_a_id"])},
        )
        assert resp.status_code == 200
        assert resp.json()["fragmento"] == ""

    async def test_fragmento_lms_con_fechas(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        await self._create_fecha(async_client, token, d, tipo="Parcial", numero=1, titulo="1er Parcial", fecha="2026-04-15")
        await self._create_fecha(async_client, token, d, tipo="TP", numero=1, titulo="TP 1", fecha="2026-03-30")
        await self._create_fecha(async_client, token, d, tipo="Coloquio", numero=1, titulo="Coloquio Final", fecha="2026-06-20")

        resp = await async_client.get(
            "/api/v1/fechas-academicas/fragmento-lms",
            headers=_auth(token),
            params={"materia_id": str(d["materia_a_id"]), "cohorte_id": str(d["cohorte_a_id"])},
        )
        assert resp.status_code == 200
        fragmento = resp.json()["fragmento"]
        assert "Programación I" in fragmento
        assert "MAR-2026" in fragmento
        assert "Parciales" in fragmento
        assert "Trabajos Prácticos" in fragmento
        assert "Coloquios" in fragmento
        assert "15 de abril de 2026" in fragmento

    async def test_fragmento_lms_filtra_por_periodo(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        await self._create_fecha(async_client, token, d, tipo="Parcial", numero=1, periodo="2026-1", titulo="Parc 1 Q1", fecha="2026-04-15")
        await self._create_fecha(async_client, token, d, tipo="Parcial", numero=1, periodo="2026-2", titulo="Parc 1 Q2", fecha="2026-09-10")

        resp = await async_client.get(
            "/api/v1/fechas-academicas/fragmento-lms",
            headers=_auth(token),
            params={"materia_id": str(d["materia_a_id"]), "cohorte_id": str(d["cohorte_a_id"]), "periodo": "2026-1"},
        )
        assert resp.status_code == 200
        fragmento = resp.json()["fragmento"]
        assert "15 de abril de 2026" in fragmento
        assert "10 de septiembre de 2026" not in fragmento

    async def test_fragmento_lms_orden_canonico(self, async_client, prog_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        d = prog_db
        # Insert out of canonical order
        await self._create_fecha(async_client, token, d, tipo="Coloquio", numero=1, titulo="Col", fecha="2026-06-20")
        await self._create_fecha(async_client, token, d, tipo="Parcial", numero=2, titulo="2do Parc", fecha="2026-05-15")
        await self._create_fecha(async_client, token, d, tipo="Parcial", numero=1, titulo="1er Parc", fecha="2026-04-15")
        await self._create_fecha(async_client, token, d, tipo="TP", numero=1, titulo="TP", fecha="2026-03-30")

        resp = await async_client.get(
            "/api/v1/fechas-academicas/fragmento-lms",
            headers=_auth(token),
            params={"materia_id": str(d["materia_a_id"]), "cohorte_id": str(d["cohorte_a_id"])},
        )
        assert resp.status_code == 200
        fragmento = resp.json()["fragmento"]
        # Verify canonical section order: Parciales → TP → Coloquios
        idx_parciales = fragmento.index("Parciales")
        idx_tp = fragmento.index("Trabajos Prácticos")
        idx_col = fragmento.index("Coloquios")
        assert idx_parciales < idx_tp < idx_col
        # Within Parciales: 1er before 2do
        idx_1er = fragmento.index("15 de abril")
        idx_2do = fragmento.index("15 de mayo")
        assert idx_1er < idx_2do
