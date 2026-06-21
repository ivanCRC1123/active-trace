"""C-18 grilla-salarial — integration tests.

Covers:
- MateriaGrupo ABM (CRUD, unicidad, aislamiento tenant)
- SalarioBase ABM + vigencia query
- SalarioPlus ABM + vigencia query
- RBAC: FINANZAS → acceso; PROFESOR → 403
- Validación de monto > 0 (422)
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
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_CODE = "grilla-test-a"
OTHER_TENANT_CODE = "grilla-test-b"
USER_PASS = "Admin123!"
FINANZAS_EMAIL = "grilla.finanzas@test.edu.ar"
PROF_EMAIL = "grilla.prof@test.edu.ar"
ADMIN_B_EMAIL = "grilla.admin.b@test.edu.ar"


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def grilla_db(db_session: AsyncSession) -> dict:
    """Seed two tenants with users, roles, permissions, and a materia."""
    await db_session.execute(text("DELETE FROM materia_grupo"))
    await db_session.execute(text("DELETE FROM salario_base"))
    await db_session.execute(text("DELETE FROM salario_plus"))
    await db_session.execute(text("DELETE FROM asignacion"))
    await db_session.execute(text("TRUNCATE TABLE audit_log"))
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

    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Grilla Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    finanzas_a = _user(FINANZAS_EMAIL, tid_a)
    prof_a = _user(PROF_EMAIL, tid_a)
    db_session.add_all([finanzas_a, prof_a])
    await db_session.flush()
    await db_session.refresh(finanzas_a)
    await db_session.refresh(prof_a)

    rol_fin_a = Rol(tenant_id=tid_a, nombre="FINANZAS", descripcion="Finanzas")
    rol_prof_a = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    db_session.add_all([rol_fin_a, rol_prof_a])
    await db_session.flush()
    await db_session.refresh(rol_fin_a)

    p_grilla = Permiso(
        tenant_id=tid_a,
        codigo="grilla_salarial:operar",
        modulo="grilla_salarial",
        descripcion="Operar grilla salarial",
    )
    db_session.add(p_grilla)
    await db_session.flush()
    await db_session.refresh(p_grilla)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_fin_a.id, permiso_id=p_grilla.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=finanzas_a.id, rol_id=rol_fin_a.id),
        UserRol(tenant_id=tid_a, user_id=prof_a.id, rol_id=rol_prof_a.id),
    ])
    await db_session.flush()

    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-A", nombre="Ingeniería A")
    materia_a = Materia(tenant_id=tid_a, codigo="PROG_I", nombre="Programación I")
    db_session.add_all([carrera_a, materia_a])
    await db_session.flush()
    await db_session.refresh(materia_a)

    # ── Tenant B ──────────────────────────────────────────────────────────────

    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Grilla Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    admin_b = _user(ADMIN_B_EMAIL, tid_b)
    db_session.add(admin_b)
    await db_session.flush()
    await db_session.refresh(admin_b)

    rol_fin_b = Rol(tenant_id=tid_b, nombre="FINANZAS", descripcion="Finanzas")
    db_session.add(rol_fin_b)
    await db_session.flush()
    await db_session.refresh(rol_fin_b)

    p_grilla_b = Permiso(
        tenant_id=tid_b,
        codigo="grilla_salarial:operar",
        modulo="grilla_salarial",
        descripcion="Operar grilla salarial",
    )
    db_session.add(p_grilla_b)
    await db_session.flush()
    await db_session.refresh(p_grilla_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_fin_b.id, permiso_id=p_grilla_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=admin_b.id, rol_id=rol_fin_b.id),
    ])
    await db_session.flush()

    materia_b = Materia(tenant_id=tid_b, codigo="PROG_I", nombre="Programación I")
    db_session.add(materia_b)
    await db_session.flush()
    await db_session.refresh(materia_b)

    await db_session.commit()

    return {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "finanzas_a_id": finanzas_a.id,
        "prof_a_id": prof_a.id,
        "admin_b_id": admin_b.id,
        "materia_a_id": materia_a.id,
        "materia_b_id": materia_b.id,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── TestMateriaGrupo ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMateriaGrupo:
    async def test_create_materia_grupo_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        resp = await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token),
            json={"materia_id": str(d["materia_a_id"]), "grupo": "PROG"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["grupo"] == "PROG"
        assert body["materia_id"] == str(d["materia_a_id"])
        assert body["tenant_id"] == str(d["tenant_a_id"])

    async def test_create_materia_grupo_materia_otro_tenant_404(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        resp = await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token),
            json={"materia_id": str(d["materia_b_id"]), "grupo": "PROG"},
        )
        assert resp.status_code == 404

    async def test_create_materia_grupo_duplicado_409(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        payload = {"materia_id": str(d["materia_a_id"]), "grupo": "PROG"}
        r1 = await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos", headers=_auth(token), json=payload
        )
        assert r1.status_code == 201
        r2 = await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos", headers=_auth(token), json=payload
        )
        assert r2.status_code == 409

    async def test_list_materia_grupos_filtra_por_tenant(self, async_client, grilla_db):
        d = grilla_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token_a),
            json={"materia_id": str(d["materia_a_id"]), "grupo": "PROG"},
        )
        await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token_b),
            json={"materia_id": str(d["materia_b_id"]), "grupo": "PROG"},
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/materia-grupos", headers=_auth(token_a)
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["tenant_id"] == str(d["tenant_a_id"])

    async def test_get_materia_grupo_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        cr = await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token),
            json={"materia_id": str(d["materia_a_id"]), "grupo": "PROG"},
        )
        mg_id = cr.json()["id"]
        resp = await async_client.get(
            f"/api/v1/grilla-salarial/materia-grupos/{mg_id}", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json()["grupo"] == "PROG"

    async def test_get_materia_grupo_otro_tenant_404(self, async_client, grilla_db):
        d = grilla_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        cr = await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token_a),
            json={"materia_id": str(d["materia_a_id"]), "grupo": "PROG"},
        )
        mg_id = cr.json()["id"]
        resp = await async_client.get(
            f"/api/v1/grilla-salarial/materia-grupos/{mg_id}", headers=_auth(token_b)
        )
        assert resp.status_code == 404

    async def test_delete_materia_grupo_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        cr = await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token),
            json={"materia_id": str(d["materia_a_id"]), "grupo": "PROG"},
        )
        mg_id = cr.json()["id"]
        del_resp = await async_client.delete(
            f"/api/v1/grilla-salarial/materia-grupos/{mg_id}", headers=_auth(token)
        )
        assert del_resp.status_code == 204
        get_resp = await async_client.get(
            f"/api/v1/grilla-salarial/materia-grupos/{mg_id}", headers=_auth(token)
        )
        assert get_resp.status_code == 404

    async def test_list_materia_grupos_filter_by_grupo(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        await async_client.post(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token),
            json={"materia_id": str(d["materia_a_id"]), "grupo": "PROG"},
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/materia-grupos",
            headers=_auth(token),
            params={"grupo": "PROG"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_profesor_materia_grupos_403(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.get(
            "/api/v1/grilla-salarial/materia-grupos", headers=_auth(token)
        )
        assert resp.status_code == 403


# ── TestSalarioBase ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSalarioBase:
    def _payload(self, **overrides) -> dict:
        base = {
            "rol": "PROFESOR",
            "monto": "5000.00",
            "desde": "2026-01-01",
            "hasta": None,
        }
        base.update(overrides)
        return base

    async def test_create_salario_base_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        resp = await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["rol"] == "PROFESOR"
        assert body["monto"] == "5000.00"
        assert body["tenant_id"] == str(d["tenant_a_id"])
        assert body["hasta"] is None

    async def test_create_salario_base_monto_cero_422(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        resp = await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(monto="0"),
        )
        assert resp.status_code == 422

    async def test_create_salario_base_monto_negativo_422(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        resp = await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(monto="-100"),
        )
        assert resp.status_code == 422

    async def test_list_salario_base_by_rol(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(rol="PROFESOR"),
        )
        await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(rol="TUTOR"),
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            params={"rol": "PROFESOR"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["rol"] == "PROFESOR"

    async def test_get_salario_base_vigente_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(desde="2026-01-01", hasta=None),
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-base/vigente",
            headers=_auth(token),
            params={"rol": "PROFESOR", "fecha": "2026-06-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        assert body["rol"] == "PROFESOR"
        assert body["monto"] == "5000.00"

    async def test_get_salario_base_vigente_sin_registro(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        # Create a past record (hasta before query date)
        await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(desde="2025-01-01", hasta="2025-12-31"),
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-base/vigente",
            headers=_auth(token),
            params={"rol": "PROFESOR", "fecha": "2026-06-01"},
        )
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_update_salario_base_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(),
        )
        sb_id = cr.json()["id"]
        resp = await async_client.patch(
            f"/api/v1/grilla-salarial/salario-base/{sb_id}",
            headers=_auth(token),
            json={"monto": "6000.00"},
        )
        assert resp.status_code == 200
        assert resp.json()["monto"] == "6000.00"
        assert resp.json()["rol"] == "PROFESOR"  # unchanged

    async def test_delete_salario_base_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token),
            json=self._payload(),
        )
        sb_id = cr.json()["id"]
        del_resp = await async_client.delete(
            f"/api/v1/grilla-salarial/salario-base/{sb_id}", headers=_auth(token)
        )
        assert del_resp.status_code == 204
        get_resp = await async_client.get(
            f"/api/v1/grilla-salarial/salario-base/{sb_id}", headers=_auth(token)
        )
        assert get_resp.status_code == 404

    async def test_get_salario_base_otro_tenant_404(self, async_client, grilla_db):
        d = grilla_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        cr = await async_client.post(
            "/api/v1/grilla-salarial/salario-base",
            headers=_auth(token_a),
            json=self._payload(),
        )
        sb_id = cr.json()["id"]
        resp = await async_client.get(
            f"/api/v1/grilla-salarial/salario-base/{sb_id}", headers=_auth(token_b)
        )
        assert resp.status_code == 404

    async def test_profesor_salario_base_403(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-base", headers=_auth(token)
        )
        assert resp.status_code == 403


# ── TestSalarioPlus ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSalarioPlus:
    def _payload(self, **overrides) -> dict:
        base = {
            "grupo": "PROG",
            "rol": "PROFESOR",
            "descripcion": "Plus Programación",
            "monto": "1500.00",
            "desde": "2026-01-01",
            "hasta": None,
        }
        base.update(overrides)
        return base

    async def test_create_salario_plus_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = grilla_db
        resp = await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["grupo"] == "PROG"
        assert body["rol"] == "PROFESOR"
        assert body["monto"] == "1500.00"
        assert body["tenant_id"] == str(d["tenant_a_id"])

    async def test_create_salario_plus_monto_cero_422(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        resp = await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(monto="0"),
        )
        assert resp.status_code == 422

    async def test_list_salario_plus_by_grupo(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(grupo="PROG"),
        )
        await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(grupo="REDES"),
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            params={"grupo": "PROG"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["grupo"] == "PROG"

    async def test_list_salario_plus_by_rol(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(rol="PROFESOR"),
        )
        await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(grupo="REDES", rol="TUTOR"),
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            params={"rol": "TUTOR"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["rol"] == "TUTOR"

    async def test_get_salario_plus_vigente_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(desde="2026-01-01", hasta=None),
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-plus/vigente",
            headers=_auth(token),
            params={"grupo": "PROG", "rol": "PROFESOR", "fecha": "2026-06-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body is not None
        assert body["grupo"] == "PROG"
        assert body["monto"] == "1500.00"

    async def test_get_salario_plus_vigente_sin_registro(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(desde="2025-01-01", hasta="2025-12-31"),
        )
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-plus/vigente",
            headers=_auth(token),
            params={"grupo": "PROG", "rol": "PROFESOR", "fecha": "2026-06-01"},
        )
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_update_salario_plus_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(),
        )
        sp_id = cr.json()["id"]
        resp = await async_client.patch(
            f"/api/v1/grilla-salarial/salario-plus/{sp_id}",
            headers=_auth(token),
            json={"monto": "2000.00", "descripcion": "Plus Prog actualizado"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["monto"] == "2000.00"
        assert body["descripcion"] == "Plus Prog actualizado"
        assert body["grupo"] == "PROG"  # unchanged

    async def test_delete_salario_plus_ok(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token),
            json=self._payload(),
        )
        sp_id = cr.json()["id"]
        del_resp = await async_client.delete(
            f"/api/v1/grilla-salarial/salario-plus/{sp_id}", headers=_auth(token)
        )
        assert del_resp.status_code == 204
        get_resp = await async_client.get(
            f"/api/v1/grilla-salarial/salario-plus/{sp_id}", headers=_auth(token)
        )
        assert get_resp.status_code == 404

    async def test_get_salario_plus_otro_tenant_404(self, async_client, grilla_db):
        d = grilla_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        cr = await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token_a),
            json=self._payload(),
        )
        sp_id = cr.json()["id"]
        resp = await async_client.get(
            f"/api/v1/grilla-salarial/salario-plus/{sp_id}", headers=_auth(token_b)
        )
        assert resp.status_code == 404

    async def test_profesor_salario_plus_403(self, async_client, grilla_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-plus", headers=_auth(token)
        )
        assert resp.status_code == 403

    async def test_salario_plus_vigente_filtra_por_tenant(self, async_client, grilla_db):
        d = grilla_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        # Create plus only in tenant A
        await async_client.post(
            "/api/v1/grilla-salarial/salario-plus",
            headers=_auth(token_a),
            json=self._payload(),
        )
        # Tenant B queries vigente — should find nothing
        resp = await async_client.get(
            "/api/v1/grilla-salarial/salario-plus/vigente",
            headers=_auth(token_b),
            params={"grupo": "PROG", "rol": "PROFESOR", "fecha": "2026-06-01"},
        )
        assert resp.status_code == 200
        assert resp.json() is None
