"""C-15 avisos-y-acknowledgment — integration tests.

Covers:
- CRUD avisos (all alcances, scope validation, vigencia, soft-delete, tenant isolation)
- mis_avisos: Global visibility, PorRol filtering, PorMateria/PorCohorte via asignacion,
  vigencia window, inactive exclusion, tenant isolation, ordering
- Acknowledgment: first ack 201, idempotent 200, aviso disappears from mis_avisos after
  ack (requiere_ack=True), stays visible (requiere_ack=False), cross-tenant 404, stats
- RBAC: ALUMNO can't create, TUTOR can see mis-avisos, COORDINADOR can see stats
"""

from datetime import date, datetime, timezone, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password
from app.models.asignacion import Asignacion
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_A = "avi-test-a"
TENANT_B = "avi-test-b"
USER_PASS = "Admin123!"
ADMIN_EMAIL = "avi.admin@test.edu.ar"
COORD_EMAIL = "avi.coord@test.edu.ar"
ALUMNO_EMAIL = "avi.alumno@test.edu.ar"
TUTOR_EMAIL = "avi.tutor@test.edu.ar"
ADMIN_B_EMAIL = "avi.admin.b@test.edu.ar"

# Vigencia helpers
_NOW = datetime.now(timezone.utc)
_PAST = _NOW - timedelta(days=2)
_FAR_FUTURE = _NOW + timedelta(days=30)
_YESTERDAY = _NOW - timedelta(days=1)
_TOMORROW = _NOW + timedelta(days=1)


# ── Fixture ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def avi_db(db_session: AsyncSession) -> dict:
    """Two tenants: ADMIN+COORD+ALUMNO+TUTOR in A, ADMIN in B.
    COORD has an Asignacion to materia_a + cohorte_a.
    Both avisos:publicar and comunicacion:confirmar_aviso are seeded.
    """
    await db_session.execute(text("DELETE FROM acknowledgment_aviso"))
    await db_session.execute(text("DELETE FROM aviso"))
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

    # ── Tenant A ─────────────────────────────────────────────────────────────
    tenant_a = Tenant(codigo=TENANT_A, nombre="Avisos Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    admin_a = _user(ADMIN_EMAIL, tid_a)
    coord_a = _user(COORD_EMAIL, tid_a)
    alumno_a = _user(ALUMNO_EMAIL, tid_a)
    tutor_a = _user(TUTOR_EMAIL, tid_a)
    db_session.add_all([admin_a, coord_a, alumno_a, tutor_a])
    await db_session.flush()
    await db_session.refresh(admin_a)
    await db_session.refresh(coord_a)
    await db_session.refresh(alumno_a)
    await db_session.refresh(tutor_a)

    rol_admin_a = Rol(tenant_id=tid_a, nombre="ADMIN", descripcion="Admin")
    rol_coord_a = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    rol_alumno_a = Rol(tenant_id=tid_a, nombre="ALUMNO", descripcion="Alumno")
    rol_tutor_a = Rol(tenant_id=tid_a, nombre="TUTOR", descripcion="Tutor")
    db_session.add_all([rol_admin_a, rol_coord_a, rol_alumno_a, rol_tutor_a])
    await db_session.flush()
    await db_session.refresh(rol_admin_a)
    await db_session.refresh(rol_coord_a)
    await db_session.refresh(rol_alumno_a)
    await db_session.refresh(rol_tutor_a)

    p_publicar = Permiso(
        tenant_id=tid_a, codigo="avisos:publicar", modulo="avisos", descripcion="Publicar avisos"
    )
    p_ack = Permiso(
        tenant_id=tid_a, codigo="comunicacion:confirmar_aviso", modulo="comunicacion",
        descripcion="Confirmar aviso"
    )
    db_session.add_all([p_publicar, p_ack])
    await db_session.flush()
    await db_session.refresh(p_publicar)
    await db_session.refresh(p_ack)

    db_session.add_all([
        # ADMIN: publicar + ack
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_publicar.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_ack.id, scope="all"),
        # COORD: publicar + ack
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord_a.id, permiso_id=p_publicar.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord_a.id, permiso_id=p_ack.id, scope="all"),
        # ALUMNO: ack only (no publicar)
        RolPermiso(tenant_id=tid_a, rol_id=rol_alumno_a.id, permiso_id=p_ack.id, scope="all"),
        # TUTOR: ack only
        RolPermiso(tenant_id=tid_a, rol_id=rol_tutor_a.id, permiso_id=p_ack.id, scope="all"),
        # User-role assignments
        UserRol(tenant_id=tid_a, user_id=admin_a.id, rol_id=rol_admin_a.id),
        UserRol(tenant_id=tid_a, user_id=coord_a.id, rol_id=rol_coord_a.id),
        UserRol(tenant_id=tid_a, user_id=alumno_a.id, rol_id=rol_alumno_a.id),
        UserRol(tenant_id=tid_a, user_id=tutor_a.id, rol_id=rol_tutor_a.id),
    ])
    await db_session.flush()

    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-AVI-A", nombre="Ingeniería A")
    materia_a = Materia(tenant_id=tid_a, codigo="AVI_I", nombre="Análisis I")
    db_session.add_all([carrera_a, materia_a])
    await db_session.flush()
    await db_session.refresh(carrera_a)
    await db_session.refresh(materia_a)

    cohorte_a = Cohorte(
        tenant_id=tid_a, carrera_id=carrera_a.id,
        nombre="MAR-2026", anio=2026, vig_desde=date(2026, 3, 1),
    )
    db_session.add(cohorte_a)
    await db_session.flush()
    await db_session.refresh(cohorte_a)

    # COORD has active asignacion → materia_a + cohorte_a
    asig_coord = Asignacion(
        tenant_id=tid_a, usuario_id=coord_a.id, rol_id=rol_coord_a.id,
        materia_id=materia_a.id, cohorte_id=cohorte_a.id, carrera_id=carrera_a.id,
        desde=date(2026, 3, 1),
    )
    db_session.add(asig_coord)
    await db_session.flush()

    # ── Tenant B ─────────────────────────────────────────────────────────────
    tenant_b = Tenant(codigo=TENANT_B, nombre="Avisos Test B")
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

    p_publicar_b = Permiso(
        tenant_id=tid_b, codigo="avisos:publicar", modulo="avisos", descripcion="Publicar avisos"
    )
    p_ack_b = Permiso(
        tenant_id=tid_b, codigo="comunicacion:confirmar_aviso", modulo="comunicacion",
        descripcion="Confirmar aviso"
    )
    db_session.add_all([p_publicar_b, p_ack_b])
    await db_session.flush()
    await db_session.refresh(p_publicar_b)
    await db_session.refresh(p_ack_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_admin_b.id, permiso_id=p_publicar_b.id, scope="all"),
        RolPermiso(tenant_id=tid_b, rol_id=rol_admin_b.id, permiso_id=p_ack_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=admin_b.id, rol_id=rol_admin_b.id),
    ])
    await db_session.flush()

    carrera_b = Carrera(tenant_id=tid_b, codigo="ING-AVI-B", nombre="Ingeniería B")
    materia_b = Materia(tenant_id=tid_b, codigo="AVI_I", nombre="Análisis I")
    db_session.add_all([carrera_b, materia_b])
    await db_session.flush()
    await db_session.refresh(carrera_b)
    await db_session.refresh(materia_b)

    await db_session.commit()

    return {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "admin_a_id": admin_a.id,
        "coord_a_id": coord_a.id,
        "alumno_a_id": alumno_a.id,
        "tutor_a_id": tutor_a.id,
        "admin_b_id": admin_b.id,
        "materia_a_id": materia_a.id,
        "cohorte_a_id": cohorte_a.id,
        "materia_b_id": materia_b.id,
    }


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _aviso_payload(d: dict, **overrides) -> dict:
    base = {
        "alcance": "Global",
        "severidad": "Info",
        "titulo": "Aviso de prueba",
        "cuerpo": "Contenido del aviso.",
        "inicio_en": _PAST.isoformat(),
        "fin_en": _FAR_FUTURE.isoformat(),
    }
    base.update(overrides)
    return base


# ── TestCRUDAvisos ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCRUDAvisos:
    async def test_create_global_ok(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token), json=_aviso_payload(avi_db)
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["alcance"] == "Global"
        assert body["titulo"] == "Aviso de prueba"
        assert body["tenant_id"] == str(avi_db["tenant_a_id"])

    async def test_create_por_materia_ok(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token),
            json=_aviso_payload(avi_db, alcance="PorMateria", materia_id=str(avi_db["materia_a_id"])),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["materia_id"] == str(avi_db["materia_a_id"])

    async def test_create_por_cohorte_ok(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token),
            json=_aviso_payload(avi_db, alcance="PorCohorte", cohorte_id=str(avi_db["cohorte_a_id"])),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["cohorte_id"] == str(avi_db["cohorte_a_id"])

    async def test_create_por_rol_ok(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token),
            json=_aviso_payload(avi_db, alcance="PorRol", rol_destino="ALUMNO"),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["rol_destino"] == "ALUMNO"

    async def test_create_missing_scope_field_returns_422(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        # PorMateria without materia_id
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token),
            json=_aviso_payload(avi_db, alcance="PorMateria"),
        )
        assert resp.status_code == 422

    async def test_create_fin_before_inicio_returns_422(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token),
            json=_aviso_payload(
                avi_db,
                inicio_en=_FAR_FUTURE.isoformat(),
                fin_en=_PAST.isoformat(),
            ),
        )
        assert resp.status_code == 422

    async def test_create_invalid_rol_destino_returns_422(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token),
            json=_aviso_payload(avi_db, alcance="PorRol", rol_destino="INVENTADO"),
        )
        assert resp.status_code == 422

    async def test_list_filtra_por_tenant(self, async_client, avi_db):
        token_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        await async_client.post("/api/v1/avisos/", headers=_auth(token_a), json=_aviso_payload(avi_db))
        await async_client.post("/api/v1/avisos/", headers=_auth(token_b), json=_aviso_payload(avi_db))
        resp = await async_client.get("/api/v1/avisos/", headers=_auth(token_a))
        assert resp.status_code == 200
        items = resp.json()
        assert all(i["tenant_id"] == str(avi_db["tenant_a_id"]) for i in items)
        assert len(items) == 1

    async def test_soft_delete(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        cr = await async_client.post("/api/v1/avisos/", headers=_auth(token), json=_aviso_payload(avi_db))
        av_id = cr.json()["id"]
        del_resp = await async_client.delete(f"/api/v1/avisos/{av_id}", headers=_auth(token))
        assert del_resp.status_code == 204
        get_resp = await async_client.get(f"/api/v1/avisos/{av_id}", headers=_auth(token))
        assert get_resp.status_code == 404

    async def test_update_titulo(self, async_client, avi_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        cr = await async_client.post("/api/v1/avisos/", headers=_auth(token), json=_aviso_payload(avi_db))
        av_id = cr.json()["id"]
        upd = await async_client.patch(
            f"/api/v1/avisos/{av_id}", headers=_auth(token), json={"titulo": "Nuevo título"}
        )
        assert upd.status_code == 200
        assert upd.json()["titulo"] == "Nuevo título"


# ── TestMisAvisos ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMisAvisos:
    async def test_global_visible_to_alumno(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        await async_client.post("/api/v1/avisos/", headers=_auth(token_admin), json=_aviso_payload(avi_db))
        resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_por_rol_filters_correctly(self, async_client, avi_db):
        """PorRol=COORDINADOR visible only to COORD, not ALUMNO."""
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_coord = await _login(async_client, TENANT_A, COORD_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)

        await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, alcance="PorRol", rol_destino="COORDINADOR"),
        )
        coord_resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_coord))
        alumno_resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert len(coord_resp.json()) == 1
        assert len(alumno_resp.json()) == 0

    async def test_por_materia_visible_via_asignacion(self, async_client, avi_db):
        """PorMateria=materia_a visible to COORD who has Asignacion there."""
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_coord = await _login(async_client, TENANT_A, COORD_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)

        await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, alcance="PorMateria", materia_id=str(avi_db["materia_a_id"])),
        )
        coord_resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_coord))
        alumno_resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert len(coord_resp.json()) == 1
        assert len(alumno_resp.json()) == 0

    async def test_vigencia_window_excludes_expired(self, async_client, avi_db):
        """Expired aviso (fin_en in the past) does not appear in mis_avisos."""
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)

        expired_inicio = _NOW - timedelta(days=5)
        expired_fin = _NOW - timedelta(days=1)
        await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(
                avi_db,
                inicio_en=expired_inicio.isoformat(),
                fin_en=expired_fin.isoformat(),
            ),
        )
        resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert len(resp.json()) == 0

    async def test_inactive_not_shown(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, activo=True),
        )
        av_id = cr.json()["id"]
        # Deactivate
        await async_client.patch(
            f"/api/v1/avisos/{av_id}", headers=_auth(token_admin), json={"activo": False}
        )
        resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert len(resp.json()) == 0

    async def test_tenant_isolation_in_mis_avisos(self, async_client, avi_db):
        """Aviso from tenant B is not visible to user in tenant A."""
        token_admin_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_admin_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        await async_client.post("/api/v1/avisos/", headers=_auth(token_admin_b), json=_aviso_payload(avi_db))
        resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_admin_a))
        assert len(resp.json()) == 0

    async def test_order_by_orden_then_inicio_en(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, titulo="Aviso orden=5", orden=5),
        )
        await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, titulo="Aviso orden=1", orden=1),
        )
        resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert resp.status_code == 200
        titles = [i["titulo"] for i in resp.json()]
        assert titles[0] == "Aviso orden=1"
        assert titles[1] == "Aviso orden=5"


# ── TestAcknowledgment ────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestAcknowledgment:
    async def test_first_ack_returns_201(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, requiere_ack=True),
        )
        av_id = cr.json()["id"]
        ack_resp = await async_client.post(
            f"/api/v1/avisos/{av_id}/ack", headers=_auth(token_alumno)
        )
        assert ack_resp.status_code == 201, ack_resp.text
        body = ack_resp.json()
        assert body["aviso_id"] == av_id
        assert "created_at" in body

    async def test_second_ack_is_idempotent_200(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, requiere_ack=True),
        )
        av_id = cr.json()["id"]
        await async_client.post(f"/api/v1/avisos/{av_id}/ack", headers=_auth(token_alumno))
        ack2 = await async_client.post(f"/api/v1/avisos/{av_id}/ack", headers=_auth(token_alumno))
        assert ack2.status_code == 200

    async def test_aviso_disappears_after_ack_when_requiere_ack(self, async_client, avi_db):
        """requiere_ack=True: after ack the aviso should NOT appear in mis_avisos."""
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, requiere_ack=True),
        )
        av_id = cr.json()["id"]
        # Before ack — visible
        before = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert len(before.json()) == 1
        # Ack it
        await async_client.post(f"/api/v1/avisos/{av_id}/ack", headers=_auth(token_alumno))
        # After ack — gone
        after = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert len(after.json()) == 0

    async def test_aviso_stays_visible_when_not_requiere_ack(self, async_client, avi_db):
        """requiere_ack=False: aviso remains in mis_avisos even after ack."""
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, requiere_ack=False),
        )
        av_id = cr.json()["id"]
        await async_client.post(f"/api/v1/avisos/{av_id}/ack", headers=_auth(token_alumno))
        after = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_alumno))
        assert len(after.json()) == 1

    async def test_ack_cross_tenant_returns_404(self, async_client, avi_db):
        """User from tenant B cannot ack an aviso from tenant A."""
        token_admin_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_admin_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin_a), json=_aviso_payload(avi_db)
        )
        av_id_a = cr.json()["id"]
        resp = await async_client.post(
            f"/api/v1/avisos/{av_id_a}/ack", headers=_auth(token_admin_b)
        )
        assert resp.status_code == 404

    async def test_stats_count_confirmaciones(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        token_tutor = await _login(async_client, TENANT_A, TUTOR_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin),
            json=_aviso_payload(avi_db, requiere_ack=True),
        )
        av_id = cr.json()["id"]
        # 0 before any ack
        stats0 = await async_client.get(f"/api/v1/avisos/{av_id}/stats", headers=_auth(token_admin))
        assert stats0.json()["confirmaciones"] == 0
        # ALUMNO acks
        await async_client.post(f"/api/v1/avisos/{av_id}/ack", headers=_auth(token_alumno))
        stats1 = await async_client.get(f"/api/v1/avisos/{av_id}/stats", headers=_auth(token_admin))
        assert stats1.json()["confirmaciones"] == 1
        # TUTOR acks
        await async_client.post(f"/api/v1/avisos/{av_id}/ack", headers=_auth(token_tutor))
        stats2 = await async_client.get(f"/api/v1/avisos/{av_id}/stats", headers=_auth(token_admin))
        assert stats2.json()["confirmaciones"] == 2


# ── TestRBAC ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRBAC:
    async def test_alumno_cannot_create_aviso(self, async_client, avi_db):
        token_alumno = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        resp = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_alumno), json=_aviso_payload(avi_db)
        )
        assert resp.status_code == 403

    async def test_tutor_can_see_mis_avisos(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_tutor = await _login(async_client, TENANT_A, TUTOR_EMAIL)
        await async_client.post("/api/v1/avisos/", headers=_auth(token_admin), json=_aviso_payload(avi_db))
        resp = await async_client.get("/api/v1/avisos/mis-avisos", headers=_auth(token_tutor))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_coordinador_can_see_stats(self, async_client, avi_db):
        token_admin = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_coord = await _login(async_client, TENANT_A, COORD_EMAIL)
        cr = await async_client.post(
            "/api/v1/avisos/", headers=_auth(token_admin), json=_aviso_payload(avi_db)
        )
        av_id = cr.json()["id"]
        resp = await async_client.get(f"/api/v1/avisos/{av_id}/stats", headers=_auth(token_coord))
        assert resp.status_code == 200
        assert "confirmaciones" in resp.json()
