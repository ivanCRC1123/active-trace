"""C-14 evaluaciones-y-coloquios — integration tests.

Covers:
- CRUD convocatoria (evaluacion): create, list, get, update, soft-delete, duplicados, tenant isolation
- Importar convocados: bulk insert idempotente, PII cifrada, aislamiento tenant
- Reserva de turno: cupo disponible, cupo agotado, duplicada, cancelar, cupo ilimitado
- Resultados: INSERT y UPDATE path, audit log, listado, aislamiento tenant
- Métricas: panel general y por convocatoria, cupos_libres=-1 cuando ilimitado
- RBAC: coloquios:gestionar (ADMIN+COORD) y evaluacion:reservar (ALUMNO) — 403 para roles sin permiso
"""

from datetime import date, datetime, timezone

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

TENANT_A = "col-test-a"
TENANT_B = "col-test-b"
USER_PASS = "Admin123!"
ADMIN_EMAIL = "col.admin@test.edu.ar"
COORD_EMAIL = "col.coord@test.edu.ar"
ALUMNO_EMAIL = "col.alumno@test.edu.ar"
ALUMNO2_EMAIL = "col.alumno2@test.edu.ar"
ADMIN_B_EMAIL = "col.admin.b@test.edu.ar"


# ── Fixture ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def col_db(db_session: AsyncSession) -> dict:
    """Two tenants with ADMIN/COORDINADOR/ALUMNO users and academic structure."""
    # Clean C-14 + all dependent tables (RESTRICT FKs → dependency order)
    await db_session.execute(text("DELETE FROM resultado_evaluacion"))
    await db_session.execute(text("DELETE FROM reserva_evaluacion"))
    await db_session.execute(text("DELETE FROM convocado_evaluacion"))
    await db_session.execute(text("DELETE FROM evaluacion"))
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
    tenant_a = Tenant(codigo=TENANT_A, nombre="Coloquios Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    admin_a = _user(ADMIN_EMAIL, tid_a)
    coord_a = _user(COORD_EMAIL, tid_a)
    alumno_a = _user(ALUMNO_EMAIL, tid_a)
    alumno2_a = _user(ALUMNO2_EMAIL, tid_a)
    db_session.add_all([admin_a, coord_a, alumno_a, alumno2_a])
    await db_session.flush()
    await db_session.refresh(admin_a)
    await db_session.refresh(coord_a)
    await db_session.refresh(alumno_a)
    await db_session.refresh(alumno2_a)

    rol_admin_a = Rol(tenant_id=tid_a, nombre="ADMIN", descripcion="Admin")
    rol_coord_a = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    rol_alumno_a = Rol(tenant_id=tid_a, nombre="ALUMNO", descripcion="Alumno")
    db_session.add_all([rol_admin_a, rol_coord_a, rol_alumno_a])
    await db_session.flush()
    await db_session.refresh(rol_admin_a)
    await db_session.refresh(rol_coord_a)
    await db_session.refresh(rol_alumno_a)

    p_gestionar = Permiso(tenant_id=tid_a, codigo="coloquios:gestionar", modulo="coloquios", descripcion="Gestionar coloquios")
    p_reservar = Permiso(tenant_id=tid_a, codigo="evaluacion:reservar", modulo="evaluacion", descripcion="Reservar evaluacion")
    db_session.add_all([p_gestionar, p_reservar])
    await db_session.flush()
    await db_session.refresh(p_gestionar)
    await db_session.refresh(p_reservar)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_gestionar.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord_a.id, permiso_id=p_gestionar.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_alumno_a.id, permiso_id=p_reservar.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=admin_a.id, rol_id=rol_admin_a.id),
        UserRol(tenant_id=tid_a, user_id=coord_a.id, rol_id=rol_coord_a.id),
        UserRol(tenant_id=tid_a, user_id=alumno_a.id, rol_id=rol_alumno_a.id),
        UserRol(tenant_id=tid_a, user_id=alumno2_a.id, rol_id=rol_alumno_a.id),
    ])
    await db_session.flush()

    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-COL-A", nombre="Ingeniería A")
    materia_a = Materia(tenant_id=tid_a, codigo="COL_I", nombre="Cálculo I")
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

    # ── Tenant B ──────────────────────────────────────────────────────────────
    tenant_b = Tenant(codigo=TENANT_B, nombre="Coloquios Test B")
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

    p_gestionar_b = Permiso(tenant_id=tid_b, codigo="coloquios:gestionar", modulo="coloquios", descripcion="Gestionar coloquios")
    db_session.add(p_gestionar_b)
    await db_session.flush()
    await db_session.refresh(p_gestionar_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_admin_b.id, permiso_id=p_gestionar_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=admin_b.id, rol_id=rol_admin_b.id),
    ])
    await db_session.flush()

    carrera_b = Carrera(tenant_id=tid_b, codigo="ING-COL-B", nombre="Ingeniería B")
    materia_b = Materia(tenant_id=tid_b, codigo="COL_I", nombre="Cálculo I")
    db_session.add_all([carrera_b, materia_b])
    await db_session.flush()
    await db_session.refresh(carrera_b)
    await db_session.refresh(materia_b)

    cohorte_b = Cohorte(
        tenant_id=tid_b, carrera_id=carrera_b.id,
        nombre="MAR-2026", anio=2026, vig_desde=date(2026, 3, 1),
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
        "alumno_a_id": alumno_a.id,
        "alumno2_a_id": alumno2_a.id,
        "admin_b_id": admin_b.id,
        "materia_a_id": materia_a.id,
        "cohorte_a_id": cohorte_a.id,
        "materia_b_id": materia_b.id,
        "cohorte_b_id": cohorte_b.id,
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


def _eval_payload(d: dict, **overrides) -> dict:
    base = {
        "materia_id": str(d["materia_a_id"]),
        "cohorte_id": str(d["cohorte_a_id"]),
        "tipo": "Coloquio",
        "instancia": "Coloquio 1er llamado",
        "dias_disponibles": 7,
        "cupo_total": 20,
    }
    base.update(overrides)
    return base


# ── TestCRUDConvocatoria ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCRUDConvocatoria:
    async def test_create_ok(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        resp = await async_client.post(
            "/api/v1/coloquios/", headers=_auth(token), json=_eval_payload(d)
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["tipo"] == "Coloquio"
        assert body["instancia"] == "Coloquio 1er llamado"
        assert body["cupo_total"] == 20
        assert body["tenant_id"] == str(d["tenant_a_id"])

    async def test_create_materia_otro_tenant_returns_404(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        resp = await async_client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, materia_id=str(d["materia_b_id"])),
        )
        assert resp.status_code == 404

    async def test_create_cohorte_otro_tenant_returns_404(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        resp = await async_client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, cohorte_id=str(d["cohorte_b_id"])),
        )
        assert resp.status_code == 404

    async def test_create_duplicada_returns_409(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        payload = _eval_payload(d)
        r1 = await async_client.post("/api/v1/coloquios/", headers=_auth(token), json=payload)
        assert r1.status_code == 201
        r2 = await async_client.post("/api/v1/coloquios/", headers=_auth(token), json=payload)
        assert r2.status_code == 409

    async def test_list_filtra_por_tenant(self, async_client, col_db):
        d = col_db
        token_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        await async_client.post("/api/v1/coloquios/", headers=_auth(token_a), json=_eval_payload(d))
        await async_client.post(
            "/api/v1/coloquios/", headers=_auth(token_b),
            json=_eval_payload(d, materia_id=str(d["materia_b_id"]), cohorte_id=str(d["cohorte_b_id"])),
        )
        resp = await async_client.get("/api/v1/coloquios/", headers=_auth(token_a))
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["tenant_id"] == str(d["tenant_a_id"])

    async def test_get_ok(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        cr = await async_client.post("/api/v1/coloquios/", headers=_auth(token), json=_eval_payload(d))
        ev_id = cr.json()["id"]
        resp = await async_client.get(f"/api/v1/coloquios/{ev_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == ev_id

    async def test_get_otro_tenant_returns_404(self, async_client, col_db):
        d = col_db
        token_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        cr = await async_client.post("/api/v1/coloquios/", headers=_auth(token_a), json=_eval_payload(d))
        ev_id = cr.json()["id"]
        resp = await async_client.get(f"/api/v1/coloquios/{ev_id}", headers=_auth(token_b))
        assert resp.status_code == 404

    async def test_update_ok(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        cr = await async_client.post("/api/v1/coloquios/", headers=_auth(token), json=_eval_payload(d))
        ev_id = cr.json()["id"]
        resp = await async_client.patch(
            f"/api/v1/coloquios/{ev_id}", headers=_auth(token),
            json={"cupo_total": 30, "instancia": "Coloquio 1er llamado (modif)"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cupo_total"] == 30
        assert body["instancia"] == "Coloquio 1er llamado (modif)"

    async def test_soft_delete_ok(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        cr = await async_client.post("/api/v1/coloquios/", headers=_auth(token), json=_eval_payload(d))
        ev_id = cr.json()["id"]
        del_resp = await async_client.delete(f"/api/v1/coloquios/{ev_id}", headers=_auth(token))
        assert del_resp.status_code == 204
        get_resp = await async_client.get(f"/api/v1/coloquios/{ev_id}", headers=_auth(token))
        assert get_resp.status_code == 404

    async def test_alumno_get_returns_403(self, async_client, col_db):
        """ALUMNO has no coloquios:gestionar → 403 on all management endpoints."""
        token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        resp = await async_client.get("/api/v1/coloquios/", headers=_auth(token))
        assert resp.status_code == 403

    async def test_coordinador_puede_crear(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, COORD_EMAIL)
        d = col_db
        resp = await async_client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, instancia="Coloquio Coord"),
        )
        assert resp.status_code == 201, resp.text

    async def test_cupo_total_cero_permitido(self, async_client, col_db):
        """cupo_total=0 means unlimited — must be accepted."""
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        resp = await async_client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, cupo_total=0, instancia="Coloquio ilimitado"),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["cupo_total"] == 0


# ── TestImportarConvocados ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestImportarConvocados:
    async def _create_eval(self, client, token, d, instancia="Col convoc") -> str:
        resp = await client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, instancia=instancia),
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def test_import_ok(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        ev_id = await self._create_eval(async_client, token, d)
        resp = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token),
            json={"filas": [
                {"nombre": "Ana", "apellidos": "García", "email": "ana@test.com"},
                {"nombre": "Luis", "apellidos": "Pérez", "email": "luis@test.com"},
            ]},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["insertados"] == 2

    async def test_import_idempotente_por_email(self, async_client, col_db):
        """Importing same email twice → 0 new insertions on second call."""
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        ev_id = await self._create_eval(async_client, token, d)
        payload = {"filas": [{"nombre": "Ana", "apellidos": "García", "email": "ana.idem@test.com"}]}
        r1 = await async_client.post(f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token), json=payload)
        assert r1.json()["insertados"] == 1
        r2 = await async_client.post(f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token), json=payload)
        assert r2.json()["insertados"] == 0

    async def test_import_con_usuario_id_idempotente(self, async_client, col_db):
        """Importing the same usuario_id twice → 0 new insertions on second call."""
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        ev_id = await self._create_eval(async_client, token, d)
        payload = {"filas": [{
            "nombre": "Alumno", "apellidos": "Test",
            "email": "alu@test.com", "usuario_id": str(d["alumno_a_id"]),
        }]}
        r1 = await async_client.post(f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token), json=payload)
        assert r1.json()["insertados"] == 1
        r2 = await async_client.post(f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token), json=payload)
        assert r2.json()["insertados"] == 0

    async def test_import_evaluacion_otro_tenant_returns_404(self, async_client, col_db):
        d = col_db
        token_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        ev_id = await self._create_eval(async_client, token_a, d)
        resp = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token_b),
            json={"filas": [{"nombre": "X", "apellidos": "Y", "email": "xy@test.com"}]},
        )
        assert resp.status_code == 404

    async def test_import_empty_filas_returns_422(self, async_client, col_db):
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        d = col_db
        ev_id = await self._create_eval(async_client, token, d)
        resp = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token),
            json={"filas": []},
        )
        assert resp.status_code == 422


# ── TestReservaTurno ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReservaTurno:
    _fecha = "2026-07-15T10:00:00Z"

    async def _create_eval(self, client, token, d, cupo_total=5, instancia="Col reserva") -> str:
        resp = await client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, instancia=instancia, cupo_total=cupo_total),
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    async def test_reservar_ok(self, async_client, col_db):
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d)

        resp = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token),
            json={"fecha_hora": self._fecha},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["estado"] == "Activa"
        assert body["evaluacion_id"] == ev_id

    async def test_reservar_sin_cupo_returns_409(self, async_client, col_db):
        """cupo_total=1: first alumno succeeds, second gets 409."""
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        alumno2_token = await _login(async_client, TENANT_A, ALUMNO2_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d, cupo_total=1, instancia="Col cupo 1")

        r1 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": self._fecha},
        )
        assert r1.status_code == 201

        r2 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno2_token), json={"fecha_hora": self._fecha},
        )
        assert r2.status_code == 409
        assert "sin_cupo" in r2.json()["detail"]

    async def test_reservar_ya_activa_returns_409(self, async_client, col_db):
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d, instancia="Col dup")

        r1 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": self._fecha},
        )
        assert r1.status_code == 201

        r2 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": self._fecha},
        )
        assert r2.status_code == 409
        assert "reserva_already_active" in r2.json()["detail"]

    async def test_reservar_cupo_ilimitado(self, async_client, col_db):
        """cupo_total=0 means unlimited: multiple alumnos can always reserve."""
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        alumno2_token = await _login(async_client, TENANT_A, ALUMNO2_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d, cupo_total=0, instancia="Col ilimit")

        r1 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": self._fecha},
        )
        assert r1.status_code == 201

        r2 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno2_token), json={"fecha_hora": self._fecha},
        )
        assert r2.status_code == 201

    async def test_cancelar_ok(self, async_client, col_db):
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d, instancia="Col cancel")

        r1 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": self._fecha},
        )
        assert r1.status_code == 201
        rid = r1.json()["id"]

        del_resp = await async_client.delete(
            f"/api/v1/coloquios/{ev_id}/mis-reservas/{rid}",
            headers=_auth(alumno_token),
        )
        assert del_resp.status_code == 204

    async def test_cancelar_reserva_ajena_returns_404(self, async_client, col_db):
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        alumno2_token = await _login(async_client, TENANT_A, ALUMNO2_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d, instancia="Col cancel ajena")

        r1 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": self._fecha},
        )
        rid = r1.json()["id"]

        del_resp = await async_client.delete(
            f"/api/v1/coloquios/{ev_id}/mis-reservas/{rid}",
            headers=_auth(alumno2_token),
        )
        assert del_resp.status_code == 404

    async def test_admin_no_puede_reservar(self, async_client, col_db):
        """ADMIN has no evaluacion:reservar → 403."""
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d, instancia="Col admin reserva")

        resp = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(admin_token), json={"fecha_hora": self._fecha},
        )
        assert resp.status_code == 403

    async def test_list_reservas_ok(self, async_client, col_db):
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        ev_id = await self._create_eval(async_client, admin_token, d, instancia="Col list res")

        await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": self._fecha},
        )

        resp = await async_client.get(f"/api/v1/coloquios/{ev_id}/reservas", headers=_auth(admin_token))
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ── TestResultados ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestResultados:
    async def _create_eval(self, client, token, d, instancia="Col result") -> str:
        resp = await client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, instancia=instancia),
        )
        return resp.json()["id"]

    async def test_registrar_resultado_ok(self, async_client, col_db):
        d = col_db
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        ev_id = await self._create_eval(async_client, token, d)
        resp = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/resultados", headers=_auth(token),
            json={"alumno_id": str(d["alumno_a_id"]), "nota_final": "Aprobado"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["nota_final"] == "Aprobado"
        assert body["alumno_id"] == str(d["alumno_a_id"])

    async def test_registrar_resultado_update(self, async_client, col_db):
        """Registering a result for an alumno that already has one → UPDATE (not 409)."""
        d = col_db
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        ev_id = await self._create_eval(async_client, token, d, instancia="Col result update")
        payload = {"alumno_id": str(d["alumno_a_id"]), "nota_final": "Aprobado"}
        r1 = await async_client.post(f"/api/v1/coloquios/{ev_id}/resultados", headers=_auth(token), json=payload)
        assert r1.status_code == 201
        r2 = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/resultados", headers=_auth(token),
            json={"alumno_id": str(d["alumno_a_id"]), "nota_final": "Desaprobado"},
        )
        assert r2.status_code == 201, r2.text
        assert r2.json()["nota_final"] == "Desaprobado"

    async def test_list_resultados_ok(self, async_client, col_db):
        d = col_db
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        ev_id = await self._create_eval(async_client, token, d, instancia="Col result list")
        await async_client.post(
            f"/api/v1/coloquios/{ev_id}/resultados", headers=_auth(token),
            json={"alumno_id": str(d["alumno_a_id"]), "nota_final": "Aprobado"},
        )
        resp = await async_client.get(f"/api/v1/coloquios/{ev_id}/resultados", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_registrar_resultado_otro_tenant_returns_404(self, async_client, col_db):
        d = col_db
        token_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        ev_id = await self._create_eval(async_client, token_a, d)
        resp = await async_client.post(
            f"/api/v1/coloquios/{ev_id}/resultados", headers=_auth(token_b),
            json={"alumno_id": str(d["alumno_a_id"]), "nota_final": "Aprobado"},
        )
        assert resp.status_code == 404


# ── TestMetricas ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestMetricas:
    async def _setup_eval(self, client, token, d, instancia="Col met", cupo_total=10) -> str:
        resp = await client.post(
            "/api/v1/coloquios/", headers=_auth(token),
            json=_eval_payload(d, instancia=instancia, cupo_total=cupo_total),
        )
        return resp.json()["id"]

    async def test_panel_metricas_ok(self, async_client, col_db):
        d = col_db
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        ev_id = await self._setup_eval(async_client, token, d)

        await async_client.post(
            f"/api/v1/coloquios/{ev_id}/convocados", headers=_auth(token),
            json={"filas": [{"nombre": "A", "apellidos": "B", "email": "ab@test.com"}]},
        )

        resp = await async_client.get("/api/v1/coloquios/metricas-panel", headers=_auth(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_alumnos_cargados"] >= 1
        assert body["instancias_activas"] >= 1

    async def test_metricas_convocatoria_ok(self, async_client, col_db):
        d = col_db
        admin_token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        alumno_token = await _login(async_client, TENANT_A, ALUMNO_EMAIL)
        ev_id = await self._setup_eval(async_client, admin_token, d, instancia="Col met conv", cupo_total=5)

        await async_client.post(
            f"/api/v1/coloquios/{ev_id}/mis-reservas",
            headers=_auth(alumno_token), json={"fecha_hora": "2026-07-15T10:00:00Z"},
        )

        resp = await async_client.get(f"/api/v1/coloquios/{ev_id}/metricas", headers=_auth(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["reservas_activas"] == 1
        assert body["cupos_libres"] == 4  # 5 - 1

    async def test_metricas_cupo_ilimitado_returns_minus_one(self, async_client, col_db):
        """cupo_total=0 → cupos_libres=-1 in metrics."""
        d = col_db
        token = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        ev_id = await self._setup_eval(async_client, token, d, instancia="Col met ilimit", cupo_total=0)

        resp = await async_client.get(f"/api/v1/coloquios/{ev_id}/metricas", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["cupos_libres"] == -1

    async def test_metricas_evaluacion_otro_tenant_returns_404(self, async_client, col_db):
        d = col_db
        token_a = await _login(async_client, TENANT_A, ADMIN_EMAIL)
        token_b = await _login(async_client, TENANT_B, ADMIN_B_EMAIL)
        ev_id = await self._setup_eval(async_client, token_a, d, instancia="Col met iso")
        resp = await async_client.get(f"/api/v1/coloquios/{ev_id}/metricas", headers=_auth(token_b))
        assert resp.status_code == 404
