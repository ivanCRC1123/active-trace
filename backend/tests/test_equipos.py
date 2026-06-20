"""C-08 equipos-docentes — integration tests.

Covers:
- F4.2 mis-equipos (JWT identity only — no permission guard)
- F4.3 list-equipo (equipos:asignar)
- F4.4 masiva (equipos:asignar, all-or-nothing)
- F4.5 clonar (RN-12, idempotente)
- F4.6 vigencia-bloque (bulk UPDATE por contexto)
- F4.7 exportar CSV
- Multi-tenant isolation (cross-tenant → empty / 404 / 0)
"""

from datetime import date, timedelta

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

TENANT_CODE = "eq-test-a"
OTHER_TENANT_CODE = "eq-test-b"
USER_PASS = "Admin123!"

COORD_EMAIL = "eq.coord@test.edu.ar"
NO_PERM_EMAIL = "eq.noperm@test.edu.ar"
DOC1_EMAIL = "eq.doc1@test.edu.ar"
DOC2_EMAIL = "eq.doc2@test.edu.ar"
DOC3_EMAIL = "eq.doc3@test.edu.ar"
DOC4_EMAIL = "eq.doc4@test.edu.ar"
DOC5_EMAIL = "eq.doc5@test.edu.ar"
COORD_B_EMAIL = "eq.coord.b@test.edu.ar"

TODAY = date.today()


@pytest_asyncio.fixture
async def equipos_db(db_session: AsyncSession) -> dict:
    """Seed two tenants with users, roles, permissions, and academic context.

    Tenant A:
      - coord: COORDINADOR with equipos:asignar
      - no_perm: PROFESOR without perm
      - doc1..doc5: PROFESOR
      - materia_a, carrera_a, cohorte_a1 (5 vigentes + 1 vencida), cohorte_a2 (empty)
    Tenant B:
      - coord_b: COORDINADOR with equipos:asignar
      - carrera_b, cohorte_b1
    """
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
            apellidos="Docente",
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
        )

    # ── Tenant A ──────────────────────────────────────────────────────
    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Equipo Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    coord = _user(COORD_EMAIL, tid_a)
    no_perm = _user(NO_PERM_EMAIL, tid_a)
    doc1, doc2, doc3, doc4, doc5 = [_user(e, tid_a) for e in [DOC1_EMAIL, DOC2_EMAIL, DOC3_EMAIL, DOC4_EMAIL, DOC5_EMAIL]]
    db_session.add_all([coord, no_perm, doc1, doc2, doc3, doc4, doc5])
    await db_session.flush()
    for u in (coord, no_perm, doc1, doc2, doc3, doc4, doc5):
        await db_session.refresh(u)

    rol_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coord")
    rol_prof = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    db_session.add_all([rol_coord, rol_prof])
    await db_session.flush()
    for r in (rol_coord, rol_prof):
        await db_session.refresh(r)

    p_asig = Permiso(tenant_id=tid_a, codigo="equipos:asignar", modulo="equipos", descripcion="Asignar")
    db_session.add(p_asig)
    await db_session.flush()
    await db_session.refresh(p_asig)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord.id, permiso_id=p_asig.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=coord.id, rol_id=rol_coord.id),
        UserRol(tenant_id=tid_a, user_id=no_perm.id, rol_id=rol_prof.id),
        *[UserRol(tenant_id=tid_a, user_id=u.id, rol_id=rol_prof.id) for u in (doc1, doc2, doc3, doc4, doc5)],
    ])
    await db_session.flush()

    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-A", nombre="Ingenieria A")
    materia_a = Materia(tenant_id=tid_a, codigo="MAT1", nombre="Matematica I")
    db_session.add_all([carrera_a, materia_a])
    await db_session.flush()
    for e in (carrera_a, materia_a):
        await db_session.refresh(e)

    cohorte_a1 = Cohorte(
        tenant_id=tid_a, carrera_id=carrera_a.id,
        nombre="2025-1", anio=2025,
        vig_desde=TODAY - timedelta(days=180),
    )
    cohorte_a2 = Cohorte(
        tenant_id=tid_a, carrera_id=carrera_a.id,
        nombre="2025-2", anio=2025,
        vig_desde=TODAY - timedelta(days=30),
    )
    db_session.add_all([cohorte_a1, cohorte_a2])
    await db_session.flush()
    for c in (cohorte_a1, cohorte_a2):
        await db_session.refresh(c)

    def _asig(uid, rid, coh_id, delta_desde, delta_hasta=None) -> Asignacion:
        hasta = (TODAY + timedelta(days=delta_hasta)) if delta_hasta is not None else None
        return Asignacion(
            tenant_id=tid_a,
            usuario_id=uid,
            rol_id=rid,
            materia_id=materia_a.id,
            carrera_id=carrera_a.id,
            cohorte_id=coh_id,
            desde=TODAY + timedelta(days=delta_desde),
            hasta=hasta,
            comisiones=[],
        )

    # 5 vigentes in cohorte_a1
    av1 = _asig(doc1.id, rol_prof.id, cohorte_a1.id, -30, 30)
    av2 = _asig(doc2.id, rol_prof.id, cohorte_a1.id, -10, 60)
    av3 = _asig(doc3.id, rol_prof.id, cohorte_a1.id, -5)  # open-ended
    av4 = _asig(doc4.id, rol_prof.id, cohorte_a1.id, -15, 45)
    av5 = _asig(doc5.id, rol_prof.id, cohorte_a1.id, -20, 90)
    # 1 vencida in cohorte_a1 (doc1's expired assignment)
    avenc = _asig(doc1.id, rol_prof.id, cohorte_a1.id, -90, -1)

    db_session.add_all([av1, av2, av3, av4, av5, avenc])
    await db_session.flush()
    for a in (av1, av2, av3, av4, av5, avenc):
        await db_session.refresh(a)

    # ── Tenant B ──────────────────────────────────────────────────────
    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Equipo Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    coord_b = _user(COORD_B_EMAIL, tid_b)
    db_session.add(coord_b)
    await db_session.flush()
    await db_session.refresh(coord_b)

    rol_coord_b = Rol(tenant_id=tid_b, nombre="COORDINADOR", descripcion="Coord B")
    db_session.add(rol_coord_b)
    await db_session.flush()
    await db_session.refresh(rol_coord_b)

    p_asig_b = Permiso(tenant_id=tid_b, codigo="equipos:asignar", modulo="equipos", descripcion="Asignar")
    db_session.add(p_asig_b)
    await db_session.flush()
    await db_session.refresh(p_asig_b)

    carrera_b = Carrera(tenant_id=tid_b, codigo="ING-B", nombre="Ingenieria B")
    db_session.add(carrera_b)
    await db_session.flush()
    await db_session.refresh(carrera_b)

    cohorte_b1 = Cohorte(
        tenant_id=tid_b, carrera_id=carrera_b.id,
        nombre="2025-1", anio=2025,
        vig_desde=TODAY - timedelta(days=180),
    )
    db_session.add(cohorte_b1)
    await db_session.flush()
    await db_session.refresh(cohorte_b1)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_coord_b.id, permiso_id=p_asig_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=coord_b.id, rol_id=rol_coord_b.id),
    ])
    await db_session.flush()
    await db_session.commit()

    return {
        # Tenant A
        "tenant_a_id": tid_a,
        "coord_id": coord.id,
        "no_perm_id": no_perm.id,
        "doc1_id": doc1.id,
        "doc2_id": doc2.id,
        "doc3_id": doc3.id,
        "doc4_id": doc4.id,
        "doc5_id": doc5.id,
        "rol_prof_id": rol_prof.id,
        "materia_a_id": materia_a.id,
        "carrera_a_id": carrera_a.id,
        "cohorte_a1_id": cohorte_a1.id,
        "cohorte_a2_id": cohorte_a2.id,
        "av1_id": av1.id,
        # Tenant B
        "tenant_b_id": tid_b,
        "coord_b_id": coord_b.id,
        "carrera_b_id": carrera_b.id,
        "cohorte_b1_id": cohorte_b1.id,
    }


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _hdrs(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── F4.2 mis-equipos ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMisEquipos:
    async def test_mis_equipos_devuelve_propias(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, DOC1_EMAIL)
        resp = await async_client.get("/api/v1/equipos/mis-equipos", headers=_hdrs(token))
        assert resp.status_code == 200
        ids = [a["usuario_id"] for a in resp.json()]
        assert all(i == str(equipos_db["doc1_id"]) for i in ids)
        assert len(resp.json()) == 2  # av1 (vigente) + avenc (vencida)

    async def test_mis_equipos_filtro_materia(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, DOC1_EMAIL)
        resp = await async_client.get(
            f"/api/v1/equipos/mis-equipos?materia_id={equipos_db['materia_a_id']}",
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_mis_equipos_filtro_vigencia(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, DOC1_EMAIL)
        resp = await async_client.get(
            "/api/v1/equipos/mis-equipos?estado_vigencia=Vigente",
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        items = resp.json()
        assert all(a["estado_vigencia"] == "Vigente" for a in items)
        assert len(items) == 1  # only av1 (avenc is vencida)

    async def test_mis_equipos_sin_auth_401(self, async_client, equipos_db):
        resp = await async_client.get("/api/v1/equipos/mis-equipos")
        assert resp.status_code == 401

    async def test_mis_equipos_cross_tenant_vacio(self, async_client, equipos_db):
        # coord_b from tenant_b should see 0 (they have no asignaciones)
        token = await _login(async_client, OTHER_TENANT_CODE, COORD_B_EMAIL)
        resp = await async_client.get("/api/v1/equipos/mis-equipos", headers=_hdrs(token))
        assert resp.status_code == 200
        assert resp.json() == []


# ── F4.3 list equipo ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestListEquipo:
    async def test_list_equipo_todos(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get("/api/v1/equipos", headers=_hdrs(token))
        assert resp.status_code == 200
        assert len(resp.json()) == 6  # av1..av5 + avenc

    async def test_list_equipo_filtro_cohorte(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get(
            f"/api/v1/equipos?cohorte_id={equipos_db['cohorte_a1_id']}",
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 6  # all 6 are in cohorte_a1

    async def test_list_equipo_filtro_vigencia(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/equipos?estado_vigencia=Vigente",
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        items = resp.json()
        assert all(a["estado_vigencia"] == "Vigente" for a in items)
        assert len(items) == 5  # av1..av5

    async def test_list_equipo_paginacion(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        r1 = await async_client.get("/api/v1/equipos?limit=2&offset=0", headers=_hdrs(token))
        r2 = await async_client.get("/api/v1/equipos?limit=2&offset=2", headers=_hdrs(token))
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert len(r1.json()) == 2
        assert len(r2.json()) == 2
        ids1 = {a["id"] for a in r1.json()}
        ids2 = {a["id"] for a in r2.json()}
        assert ids1.isdisjoint(ids2)

    async def test_list_equipo_sin_permiso_403(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, NO_PERM_EMAIL)
        resp = await async_client.get("/api/v1/equipos", headers=_hdrs(token))
        assert resp.status_code == 403


# ── F4.4 masiva ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMasiva:
    def _payload(self, d: dict, doc_ids: list, **extra) -> dict:
        base = {
            "usuario_ids": [str(i) for i in doc_ids],
            "rol_id": str(d["rol_prof_id"]),
            "cohorte_id": str(d["cohorte_a2_id"]),  # fresh context
            "materia_id": str(d["materia_a_id"]),
            "carrera_id": str(d["carrera_a_id"]),
            "desde": str(TODAY),
            "hasta": str(TODAY + timedelta(days=90)),
        }
        base.update(extra)
        return base

    async def test_masiva_crea_N_asignaciones(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._payload(equipos_db, [equipos_db["doc1_id"], equipos_db["doc2_id"]])
        resp = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["creados"] == 2
        assert len(body["asignaciones"]) == 2

    async def test_masiva_usuario_invalido_422(self, async_client, equipos_db):
        from uuid import uuid4
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._payload(equipos_db, [uuid4()])
        resp = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        assert resp.status_code == 422
        body = resp.json()
        assert "usuario_ids_invalidos" in str(body)

    async def test_masiva_duplicado_422(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        # First call succeeds
        payload = self._payload(equipos_db, [equipos_db["doc3_id"]])
        r1 = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        assert r1.status_code == 201
        # Second call same user → vigente duplicate → 422
        r2 = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        assert r2.status_code == 422
        assert "usuario_ids_duplicados" in str(r2.json())

    async def test_masiva_hasta_menor_que_desde_422(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._payload(
            equipos_db,
            [equipos_db["doc4_id"]],
            desde=str(TODAY + timedelta(days=10)),
            hasta=str(TODAY),
        )
        resp = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        assert resp.status_code == 422

    async def test_masiva_sin_permiso_403(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, NO_PERM_EMAIL)
        payload = self._payload(equipos_db, [equipos_db["doc1_id"]])
        resp = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        assert resp.status_code == 403

    async def test_masiva_registra_audit(self, async_client, equipos_db, db_session):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._payload(equipos_db, [equipos_db["doc5_id"]])
        resp = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        assert resp.status_code == 201
        # Check audit_log
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE accion = 'ASIGNACION_MODIFICAR'")
        )
        count = result.scalar_one()
        assert count >= 1


# ── F4.5 clonar (RN-12) ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestClonar:
    def _base_clonar(self, d: dict) -> dict:
        return {
            "origen": {
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a1_id"]),
            },
            "destino": {
                "materia_id": str(d["materia_a_id"]),
                "carrera_id": str(d["carrera_a_id"]),
                "cohorte_id": str(d["cohorte_a2_id"]),
            },
            "desde": str(TODAY),
            "hasta": str(TODAY + timedelta(days=180)),
        }

    async def test_clonar_equipo_exitoso(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._base_clonar(equipos_db)
        resp = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["creados"] == 5  # av1..av5 (vigentes); avenc is excluded
        assert body["omitidos"] == []

    async def test_clonar_origen_sin_vigentes(self, async_client, equipos_db):
        """Cloning from cohorte_a2 (empty) → 0 created."""
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = {
            "origen": {
                "materia_id": str(equipos_db["materia_a_id"]),
                "carrera_id": str(equipos_db["carrera_a_id"]),
                "cohorte_id": str(equipos_db["cohorte_a2_id"]),
            },
            "destino": {
                "materia_id": str(equipos_db["materia_a_id"]),
                "carrera_id": str(equipos_db["carrera_a_id"]),
                "cohorte_id": str(equipos_db["cohorte_a1_id"]),
            },
            "desde": str(TODAY),
            "hasta": str(TODAY + timedelta(days=180)),
        }
        resp = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert resp.status_code == 201
        body = resp.json()
        assert body["creados"] == 0

    async def test_clonar_omite_ya_existentes(self, async_client, equipos_db):
        """Clone then clone again → second run omits all (already vigente in destino)."""
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._base_clonar(equipos_db)
        r1 = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert r1.status_code == 201
        assert r1.json()["creados"] == 5
        # Second run: all already vigente in destino
        r2 = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert r2.status_code == 201
        body = r2.json()
        assert body["creados"] == 0
        assert len(body["omitidos"]) == 5

    async def test_clonar_no_copia_vencidas(self, async_client, equipos_db):
        """avenc (doc1 vencida en cohorte_a1) is not cloned."""
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._base_clonar(equipos_db)
        resp = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert resp.status_code == 201
        body = resp.json()
        # Total vigentes in cohorte_a1 = 5 (av1..av5); avenc excluded
        assert body["creados"] == 5

    async def test_clonar_cohorte_destino_invalido_404(self, async_client, equipos_db):
        from uuid import uuid4
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = {
            "origen": {
                "materia_id": str(equipos_db["materia_a_id"]),
                "carrera_id": str(equipos_db["carrera_a_id"]),
                "cohorte_id": str(equipos_db["cohorte_a1_id"]),
            },
            "destino": {
                "cohorte_id": str(uuid4()),
            },
            "desde": str(TODAY),
        }
        resp = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert resp.status_code == 404

    async def test_clonar_hasta_menor_que_desde_422(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._base_clonar(equipos_db)
        payload["desde"] = str(TODAY + timedelta(days=10))
        payload["hasta"] = str(TODAY)
        resp = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert resp.status_code == 422

    async def test_clonar_registra_audit(self, async_client, equipos_db, db_session):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        payload = self._base_clonar(equipos_db)
        resp = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert resp.status_code == 201
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE accion = 'ASIGNACION_MODIFICAR'")
        )
        assert result.scalar_one() >= 1

    async def test_clonar_sin_permiso_403(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, NO_PERM_EMAIL)
        resp = await async_client.post(
            "/api/v1/equipos/clonar",
            json=self._base_clonar(equipos_db),
            headers=_hdrs(token),
        )
        assert resp.status_code == 403


# ── F4.6 vigencia-bloque ─────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestVigenciaBloque:
    def _payload(self, d: dict, **extra) -> dict:
        base = {
            "cohorte_id": str(d["cohorte_a1_id"]),
            "desde": str(TODAY),
            "hasta": str(TODAY + timedelta(days=365)),
        }
        base.update(extra)
        return base

    async def test_vigencia_bloque_actualiza_cohorte(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        nueva_hasta = str(TODAY + timedelta(days=365))
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json=self._payload(equipos_db, hasta=nueva_hasta),
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["filas_afectadas"] == 6  # all 6 asignaciones in cohorte_a1

    async def test_vigencia_bloque_filtro_materia(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json={
                "materia_id": str(equipos_db["materia_a_id"]),
                "desde": str(TODAY),
                "hasta": str(TODAY + timedelta(days=180)),
            },
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        assert resp.json()["filas_afectadas"] == 6  # all in tenant A use materia_a

    async def test_vigencia_bloque_sin_matches(self, async_client, equipos_db):
        from uuid import uuid4
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json={
                "cohorte_id": str(uuid4()),  # unknown cohorte → 0 rows
                "desde": str(TODAY),
            },
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        assert resp.json()["filas_afectadas"] == 0

    async def test_vigencia_bloque_hasta_menor_que_desde_422(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json={
                "cohorte_id": str(equipos_db["cohorte_a1_id"]),
                "desde": str(TODAY + timedelta(days=10)),
                "hasta": str(TODAY),
            },
            headers=_hdrs(token),
        )
        assert resp.status_code == 422

    async def test_vigencia_bloque_contexto_vacio_422(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json={"desde": str(TODAY)},  # no context FK
            headers=_hdrs(token),
        )
        assert resp.status_code == 422

    async def test_vigencia_bloque_registra_audit(self, async_client, equipos_db, db_session):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json=self._payload(equipos_db),
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM audit_log WHERE accion = 'ASIGNACION_MODIFICAR'")
        )
        assert result.scalar_one() >= 1

    async def test_vigencia_bloque_sin_permiso_403(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, NO_PERM_EMAIL)
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json=self._payload(equipos_db),
            headers=_hdrs(token),
        )
        assert resp.status_code == 403


# ── F4.7 exportar CSV ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestExportarCSV:
    async def test_exportar_csv_contiene_encabezado(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get("/api/v1/equipos/exportar", headers=_hdrs(token))
        assert resp.status_code == 200
        lines = resp.content.decode("utf-8").splitlines()
        assert lines[0] == "apellidos,nombre,rol,materia,carrera,cohorte,comisiones,desde,hasta,estado_vigencia"

    async def test_exportar_csv_con_datos(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get("/api/v1/equipos/exportar", headers=_hdrs(token))
        assert resp.status_code == 200
        lines = resp.content.decode("utf-8").splitlines()
        assert len(lines) == 7  # 1 header + 6 asignaciones

    async def test_exportar_csv_filtro_cohorte(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get(
            f"/api/v1/equipos/exportar?cohorte_id={equipos_db['cohorte_a1_id']}",
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        lines = resp.content.decode("utf-8").splitlines()
        assert len(lines) == 7  # 1 header + 6

    async def test_exportar_csv_vacio(self, async_client, equipos_db):
        from uuid import uuid4
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get(
            f"/api/v1/equipos/exportar?cohorte_id={uuid4()}",
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        lines = [l for l in resp.content.decode("utf-8").splitlines() if l]
        assert len(lines) == 1  # only header

    async def test_exportar_csv_content_type(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get("/api/v1/equipos/exportar", headers=_hdrs(token))
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "attachment" in resp.headers.get("content-disposition", "")

    async def test_exportar_sin_permiso_403(self, async_client, equipos_db):
        token = await _login(async_client, TENANT_CODE, NO_PERM_EMAIL)
        resp = await async_client.get("/api/v1/equipos/exportar", headers=_hdrs(token))
        assert resp.status_code == 403


# ── Multi-tenant isolation ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestMultiTenantIsolacion:
    async def test_masiva_cross_tenant_usuario_invalido(self, async_client, equipos_db):
        """coord_b tries to assign a user from tenant_a → 422 (user not in tenant_b)."""
        token = await _login(async_client, OTHER_TENANT_CODE, COORD_B_EMAIL)
        payload = {
            "usuario_ids": [str(equipos_db["doc1_id"])],
            "rol_id": str(equipos_db["rol_prof_id"]),  # this rol_id is from tenant_a
            "cohorte_id": str(equipos_db["cohorte_b1_id"]),
            "desde": str(TODAY),
        }
        resp = await async_client.post("/api/v1/equipos/masiva", json=payload, headers=_hdrs(token))
        # user from tenant_a doesn't exist in tenant_b → 422
        assert resp.status_code in (404, 422)

    async def test_clonar_cross_tenant_aislado(self, async_client, equipos_db):
        """coord_b tries to clone from cohorte_a1 (tenant_a) → 404 (FK not in tenant_b)."""
        token = await _login(async_client, OTHER_TENANT_CODE, COORD_B_EMAIL)
        payload = {
            "origen": {"cohorte_id": str(equipos_db["cohorte_a1_id"])},
            "destino": {"cohorte_id": str(equipos_db["cohorte_b1_id"])},
            "desde": str(TODAY),
        }
        resp = await async_client.post("/api/v1/equipos/clonar", json=payload, headers=_hdrs(token))
        assert resp.status_code == 404

    async def test_vigencia_bloque_cross_tenant_cero(self, async_client, equipos_db):
        """coord_b patches cohorte_a1 (tenant_a context) → 0 rows affected (tenant filter)."""
        token = await _login(async_client, OTHER_TENANT_CODE, COORD_B_EMAIL)
        resp = await async_client.patch(
            "/api/v1/equipos/vigencia",
            json={
                "cohorte_id": str(equipos_db["cohorte_a1_id"]),
                "desde": str(TODAY),
                "hasta": str(TODAY + timedelta(days=365)),
            },
            headers=_hdrs(token),
        )
        assert resp.status_code == 200
        assert resp.json()["filas_afectadas"] == 0
