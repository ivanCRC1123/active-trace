"""C-07 asignaciones — integration tests.

Covers:
- ABM completo de Asignacion (CRUD + soft-delete)
- Validaciones: usuario/rol cross-tenant, rol ALUMNO bloqueado, hasta < desde
- Aislamiento multi-tenant (404 cross-tenant)
- Vigencia: Vigente / Vencida en response + filtros ?vigente=true/false
- RBAC: sin permiso → 403
"""

from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_CODE = "asig-test-a"
OTHER_TENANT_CODE = "asig-test-b"
USER_PASS = "Admin123!"
COORD_EMAIL = "asig.coord@test.edu.ar"
NO_PERM_EMAIL = "asig.noperm@test.edu.ar"
COORD_B_EMAIL = "asig.coord.b@test.edu.ar"
TARGET_EMAIL = "asig.target@test.edu.ar"


@pytest_asyncio.fixture
async def asignacion_db(db_session: AsyncSession) -> dict:
    """Seed: Tenant A — coord (has equipos:asignar), no-perm user, target user + roles.
             Tenant B — coord_b with same perm.
    """
    await db_session.execute(text("TRUNCATE TABLE asignacion"))
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

    # Tenant A
    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Asig Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    coord = _user(COORD_EMAIL, tid_a)
    no_perm = _user(NO_PERM_EMAIL, tid_a)
    target = _user(TARGET_EMAIL, tid_a)
    db_session.add_all([coord, no_perm, target])
    await db_session.flush()
    for u in (coord, no_perm, target):
        await db_session.refresh(u)

    rol_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coord")
    rol_prof = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    rol_alumno = Rol(tenant_id=tid_a, nombre="ALUMNO", descripcion="Alumno")
    db_session.add_all([rol_coord, rol_prof, rol_alumno])
    await db_session.flush()
    for r in (rol_coord, rol_prof, rol_alumno):
        await db_session.refresh(r)

    p_asig = Permiso(
        tenant_id=tid_a,
        codigo="equipos:asignar",
        modulo="equipos",
        descripcion="Asignar docentes",
    )
    db_session.add(p_asig)
    await db_session.flush()
    await db_session.refresh(p_asig)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord.id, permiso_id=p_asig.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=coord.id, rol_id=rol_coord.id),
        UserRol(tenant_id=tid_a, user_id=no_perm.id, rol_id=rol_prof.id),
    ])
    await db_session.flush()

    # Tenant B
    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Asig Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    coord_b = _user(COORD_B_EMAIL, tid_b)
    db_session.add(coord_b)
    await db_session.flush()
    await db_session.refresh(coord_b)

    rol_coord_b = Rol(tenant_id=tid_b, nombre="COORDINADOR", descripcion="Coord")
    db_session.add(rol_coord_b)
    await db_session.flush()
    await db_session.refresh(rol_coord_b)

    p_asig_b = Permiso(
        tenant_id=tid_b,
        codigo="equipos:asignar",
        modulo="equipos",
        descripcion="Asignar",
    )
    db_session.add(p_asig_b)
    await db_session.flush()
    await db_session.refresh(p_asig_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_coord_b.id, permiso_id=p_asig_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=coord_b.id, rol_id=rol_coord_b.id),
    ])
    await db_session.flush()
    await db_session.commit()

    return {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "coord_id": coord.id,
        "no_perm_id": no_perm.id,
        "coord_b_id": coord_b.id,
        "target_id": target.id,
        "rol_prof_id": rol_prof.id,
        "rol_alumno_id": rol_alumno.id,
    }


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _asig_payload(data: dict) -> dict:
    """Build an asignacion payload with sensible defaults."""
    base = {"desde": str(date.today())}
    base.update(data)
    return base


# ── TestAsignacionABM ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAsignacionABM:
    async def test_create_ok(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
            }),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert str(asignacion_db["target_id"]) == body["usuario_id"]
        assert "estado_vigencia" in body

    async def test_create_rol_alumno_400(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_alumno_id"]),
            }),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "ALUMNO" in resp.json()["detail"]

    async def test_create_hasta_menor_desde_400(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        today = date.today()
        resp = await async_client.post(
            "/api/v1/asignaciones",
            json={
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
                "desde": str(today),
                "hasta": str(today - timedelta(days=1)),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    async def test_create_usuario_otro_tenant_404(self, async_client, asignacion_db):
        """Create asignacion for user from different tenant → 404."""
        token_b = await _login(async_client, OTHER_TENANT_CODE, COORD_B_EMAIL)
        resp = await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
            }),
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404

    async def test_list_ok(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
            }),
            headers=headers,
        )
        resp = await async_client.get("/api/v1/asignaciones", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_get_ok(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
            }),
            headers=headers,
        )
        aid = created.json()["id"]
        resp = await async_client.get(f"/api/v1/asignaciones/{aid}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == aid

    async def test_get_otro_tenant_404(self, async_client, asignacion_db):
        token_a = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, COORD_B_EMAIL)
        created = await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
            }),
            headers={"Authorization": f"Bearer {token_a}"},
        )
        aid = created.json()["id"]
        resp = await async_client.get(
            f"/api/v1/asignaciones/{aid}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404

    async def test_update_ok(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
            }),
            headers=headers,
        )
        aid = created.json()["id"]
        future = str(date.today() + timedelta(days=90))
        resp = await async_client.patch(
            f"/api/v1/asignaciones/{aid}",
            json={"hasta": future, "comisiones": ["A1"]},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["hasta"] == future
        assert resp.json()["comisiones"] == ["A1"]

    async def test_soft_delete_204_luego_get_404(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = await async_client.post(
            "/api/v1/asignaciones",
            json=_asig_payload({
                "usuario_id": str(asignacion_db["target_id"]),
                "rol_id": str(asignacion_db["rol_prof_id"]),
            }),
            headers=headers,
        )
        aid = created.json()["id"]
        resp = await async_client.delete(f"/api/v1/asignaciones/{aid}", headers=headers)
        assert resp.status_code == 204
        resp2 = await async_client.get(f"/api/v1/asignaciones/{aid}", headers=headers)
        assert resp2.status_code == 404

    async def test_sin_permiso_403(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, NO_PERM_EMAIL)
        resp = await async_client.get(
            "/api/v1/asignaciones",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# ── TestVigencia ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestVigencia:
    async def _create_asig(self, client, token, target_id, rol_id, desde, hasta=None) -> dict:
        payload = {
            "usuario_id": str(target_id),
            "rol_id": str(rol_id),
            "desde": str(desde),
        }
        if hasta is not None:
            payload["hasta"] = str(hasta)
        r = await client.post(
            "/api/v1/asignaciones",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, r.text
        return r.json()

    async def test_vigente_en_rango(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        today = date.today()
        a = await self._create_asig(
            async_client, token,
            asignacion_db["target_id"], asignacion_db["rol_prof_id"],
            desde=today - timedelta(days=1), hasta=today + timedelta(days=1),
        )
        assert a["estado_vigencia"] == "Vigente"

    async def test_vencida_hasta_pasada(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        today = date.today()
        a = await self._create_asig(
            async_client, token,
            asignacion_db["target_id"], asignacion_db["rol_prof_id"],
            desde=today - timedelta(days=5), hasta=today - timedelta(days=1),
        )
        assert a["estado_vigencia"] == "Vencida"

    async def test_vigente_sin_hasta(self, async_client, asignacion_db):
        """desde <= today and no hasta → Vigente (open-ended)."""
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        a = await self._create_asig(
            async_client, token,
            asignacion_db["target_id"], asignacion_db["rol_prof_id"],
            desde=date.today(),
        )
        assert a["estado_vigencia"] == "Vigente"

    async def test_vencida_desde_futuro(self, async_client, asignacion_db):
        """desde in future → Vencida (not started yet)."""
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        a = await self._create_asig(
            async_client, token,
            asignacion_db["target_id"], asignacion_db["rol_prof_id"],
            desde=date.today() + timedelta(days=5),
        )
        assert a["estado_vigencia"] == "Vencida"

    async def test_list_vigente_true_filtra(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        today = date.today()
        await self._create_asig(
            async_client, token,
            asignacion_db["target_id"], asignacion_db["rol_prof_id"],
            desde=today - timedelta(days=1), hasta=today + timedelta(days=1),
        )
        await self._create_asig(
            async_client, token,
            asignacion_db["target_id"], asignacion_db["rol_prof_id"],
            desde=today - timedelta(days=5), hasta=today - timedelta(days=1),
        )
        resp = await async_client.get(
            "/api/v1/asignaciones?vigente=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        states = [a["estado_vigencia"] for a in resp.json()]
        assert all(s == "Vigente" for s in states)

    async def test_list_vigente_false_filtra(self, async_client, asignacion_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        today = date.today()
        await self._create_asig(
            async_client, token,
            asignacion_db["target_id"], asignacion_db["rol_prof_id"],
            desde=today - timedelta(days=5), hasta=today - timedelta(days=1),
        )
        resp = await async_client.get(
            "/api/v1/asignaciones?vigente=false",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
        states = [a["estado_vigencia"] for a in resp.json()]
        assert all(s == "Vencida" for s in states)
