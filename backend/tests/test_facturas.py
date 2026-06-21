"""C-18 facturas — integration tests (Section 3).

Covers:
- Creación rechazada si facturador=False (E20, RN-39)
- Estado: solo Pendiente|Abonada; transición bidireccional
- Al pasar a Abonada: abonada_at se setea; al volver a Pendiente: abonada_at=None
- RBAC: facturas:gestionar (FINANZAS-only); otros roles → 403
- Filtros: usuario_id, estado, periodo, fecha_desde/hasta, búsqueda libre (q)
- Aislamiento tenant: lista/get filtrados por tenant
"""

import datetime
from decimal import Decimal
from typing import AsyncGenerator

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

TENANT_CODE = "fact-test-a"
OTHER_TENANT_CODE = "fact-test-b"
USER_PASS = "Admin123!"
FINANZAS_EMAIL = "fact.finanzas@test.edu.ar"
PROF_EMAIL = "fact.prof@test.edu.ar"
DOCENTE_FACT_EMAIL = "fact.docente.f@test.edu.ar"
DOCENTE_FACT2_EMAIL = "fact.docente.f2@test.edu.ar"
DOCENTE_NO_FACT_EMAIL = "fact.docente.nf@test.edu.ar"
FINANZAS_B_EMAIL = "fact.finanzas.b@test.edu.ar"
DOCENTE_B_FACT_EMAIL = "fact.docente.b@test.edu.ar"

PERIODO = "2026-06"
PERIODO_2 = "2026-05"


# ── Fixture helpers ────────────────────────────────────────────────────────────


_TENANT_SCOPE = "SELECT id FROM tenant WHERE codigo IN ('fact-test-a', 'fact-test-b')"


async def _fact_cleanup(db_session: AsyncSession) -> None:
    """Delete ONLY rows created by fact_db, scoped to its two tenants.

    Touches nothing outside 'fact-test-a' / 'fact-test-b' so other fixtures
    (usuarios_db, analisis_db, etc.) are not disturbed.
    Called both at setup (clear stale state) and teardown (leave DB clean).
    """
    try:
        s = _TENANT_SCOPE
        # children first (FK order)
        await db_session.execute(text(f"DELETE FROM factura WHERE tenant_id IN ({s})"))
        await db_session.execute(text(f"DELETE FROM audit_log WHERE tenant_id IN ({s})"))
        await db_session.execute(text(f"DELETE FROM user_rol WHERE tenant_id IN ({s})"))
        await db_session.execute(text(f"DELETE FROM rol_permiso WHERE tenant_id IN ({s})"))
        await db_session.execute(text(f"DELETE FROM permiso WHERE tenant_id IN ({s})"))
        await db_session.execute(text(f"DELETE FROM rol WHERE tenant_id IN ({s})"))
        # refresh/recovery tokens: no tenant_id, linked through user
        u = f"SELECT id FROM \"user\" WHERE tenant_id IN ({s})"
        await db_session.execute(text(f"DELETE FROM refresh_token WHERE user_id IN ({u})"))
        await db_session.execute(text(f"DELETE FROM recovery_token WHERE user_id IN ({u})"))
        await db_session.execute(text(f'DELETE FROM "user" WHERE tenant_id IN ({s})'))
        await db_session.execute(text("DELETE FROM tenant WHERE codigo IN ('fact-test-a', 'fact-test-b')"))
        await db_session.commit()
    except Exception:
        await db_session.rollback()
        raise


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def fact_db(db_session: AsyncSession) -> AsyncGenerator[dict, None]:
    """Seed two tenants with a complete factura scenario.

    Yields a dict of IDs. Cleans up in setup AND teardown so the test
    passes deterministically even when run in isolation against a dirty DB.
    """
    await _fact_cleanup(db_session)

    def _user(email: str, tid, *, facturador: bool = False) -> User:
        return User(
            email_cifrado=encrypt(email),
            email_hash=hmac_email(email),
            password_hash=hash_password(USER_PASS),
            nombre="Test",
            apellidos="User",
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
            facturador=facturador,
        )

    # ── Tenant A ──────────────────────────────────────────────────────────────

    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Fact Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    finanzas_a = _user(FINANZAS_EMAIL, tid_a)
    prof_a = _user(PROF_EMAIL, tid_a)
    docente_fact = _user(DOCENTE_FACT_EMAIL, tid_a, facturador=True)
    docente_fact2 = _user(DOCENTE_FACT2_EMAIL, tid_a, facturador=True)
    docente_no_fact = _user(DOCENTE_NO_FACT_EMAIL, tid_a, facturador=False)
    db_session.add_all([finanzas_a, prof_a, docente_fact, docente_fact2, docente_no_fact])
    await db_session.flush()
    for u in [finanzas_a, prof_a, docente_fact, docente_fact2, docente_no_fact]:
        await db_session.refresh(u)

    rol_fin_a = Rol(tenant_id=tid_a, nombre="FINANZAS", descripcion="Finanzas")
    rol_prof_a = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    db_session.add_all([rol_fin_a, rol_prof_a])
    await db_session.flush()
    await db_session.refresh(rol_fin_a)
    await db_session.refresh(rol_prof_a)

    p_fact = Permiso(
        tenant_id=tid_a,
        codigo="facturas:gestionar",
        modulo="facturas",
        descripcion="Gestionar facturas",
    )
    db_session.add(p_fact)
    await db_session.flush()
    await db_session.refresh(p_fact)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_fin_a.id, permiso_id=p_fact.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=finanzas_a.id, rol_id=rol_fin_a.id),
        UserRol(tenant_id=tid_a, user_id=prof_a.id, rol_id=rol_prof_a.id),
    ])
    await db_session.flush()

    # ── Tenant B ──────────────────────────────────────────────────────────────

    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Fact Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    finanzas_b = _user(FINANZAS_B_EMAIL, tid_b)
    docente_b_fact = _user(DOCENTE_B_FACT_EMAIL, tid_b, facturador=True)
    db_session.add_all([finanzas_b, docente_b_fact])
    await db_session.flush()
    for u in [finanzas_b, docente_b_fact]:
        await db_session.refresh(u)

    rol_fin_b = Rol(tenant_id=tid_b, nombre="FINANZAS", descripcion="Finanzas")
    db_session.add(rol_fin_b)
    await db_session.flush()
    await db_session.refresh(rol_fin_b)

    p_fact_b = Permiso(
        tenant_id=tid_b,
        codigo="facturas:gestionar",
        modulo="facturas",
        descripcion="Gestionar facturas",
    )
    db_session.add(p_fact_b)
    await db_session.flush()
    await db_session.refresh(p_fact_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_fin_b.id, permiso_id=p_fact_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=finanzas_b.id, rol_id=rol_fin_b.id),
    ])
    await db_session.flush()

    await db_session.commit()

    yield {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "docente_fact_id": docente_fact.id,
        "docente_fact2_id": docente_fact2.id,
        "docente_no_fact_id": docente_no_fact.id,
        "docente_b_fact_id": docente_b_fact.id,
    }

    # Teardown — runs after every test (including on failure), leaving a clean DB.
    await _fact_cleanup(db_session)


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


def _payload(
    docente_id,
    *,
    periodo: str = PERIODO,
    detalle: str = "Factura servicio",
    referencia: str = "doc.pdf",
    tamano_kb: str = "120.500",
) -> dict:
    return {
        "usuario_id": str(docente_id),
        "periodo": periodo,
        "detalle": detalle,
        "referencia_archivo": referencia,
        "tamano_kb": tamano_kb,
    }


async def _crear(client: AsyncClient, token: str, docente_id, **kwargs):
    return await client.post(
        "/api/v1/facturas/",
        headers=_auth(token),
        json=_payload(docente_id, **kwargs),
    )


# ── TestFacturaCRUD ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFacturaCRUD:
    async def test_crear_factura_ok(self, async_client, fact_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        d = fact_db
        resp = await _crear(async_client, token, d["docente_fact_id"])
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["usuario_id"] == str(d["docente_fact_id"])
        assert body["periodo"] == PERIODO
        assert body["estado"] == "Pendiente"
        assert body["tenant_id"] == str(d["tenant_a_id"])
        assert body["abonada_at"] is None

    async def test_crear_factura_no_facturador_422(self, async_client, fact_db):
        """RN-39: usuario con facturador=False no puede tener facturas."""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        resp = await _crear(async_client, token, fact_db["docente_no_fact_id"])
        assert resp.status_code == 422

    async def test_crear_factura_usuario_otro_tenant_422(self, async_client, fact_db):
        """Tenant A no puede crear factura para un docente de Tenant B → 422."""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        resp = await _crear(async_client, token, fact_db["docente_b_fact_id"])
        assert resp.status_code == 422

    async def test_listar_facturas_filtra_por_tenant(self, async_client, fact_db):
        d = fact_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, FINANZAS_B_EMAIL)
        await _crear(async_client, token_a, d["docente_fact_id"])
        await _crear(async_client, token_b, d["docente_b_fact_id"])
        resp = await async_client.get("/api/v1/facturas/", headers=_auth(token_a))
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["tenant_id"] == str(d["tenant_a_id"])

    async def test_get_factura_ok(self, async_client, fact_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await _crear(async_client, token, fact_db["docente_fact_id"])
        fact_id = cr.json()["id"]
        resp = await async_client.get(f"/api/v1/facturas/{fact_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["id"] == fact_id

    async def test_get_factura_otro_tenant_404(self, async_client, fact_db):
        d = fact_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, FINANZAS_B_EMAIL)
        cr = await _crear(async_client, token_a, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        resp = await async_client.get(f"/api/v1/facturas/{fact_id}", headers=_auth(token_b))
        assert resp.status_code == 404

    async def test_editar_factura_ok(self, async_client, fact_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await _crear(async_client, token, fact_db["docente_fact_id"])
        fact_id = cr.json()["id"]
        resp = await async_client.put(
            f"/api/v1/facturas/{fact_id}",
            headers=_auth(token),
            json={"detalle": "Detalle actualizado", "tamano_kb": "200.0"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["detalle"] == "Detalle actualizado"
        assert Decimal(str(body["tamano_kb"])) == Decimal("200.0")
        assert body["periodo"] == PERIODO  # unchanged

    async def test_editar_factura_otro_tenant_404(self, async_client, fact_db):
        d = fact_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, FINANZAS_B_EMAIL)
        cr = await _crear(async_client, token_a, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        resp = await async_client.put(
            f"/api/v1/facturas/{fact_id}",
            headers=_auth(token_b),
            json={"detalle": "Hack"},
        )
        assert resp.status_code == 404

    async def test_baja_factura_ok(self, async_client, fact_db):
        """DELETE soft-delete: 204; GET posterior → 404."""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await _crear(async_client, token, fact_db["docente_fact_id"])
        fact_id = cr.json()["id"]
        del_resp = await async_client.delete(
            f"/api/v1/facturas/{fact_id}", headers=_auth(token)
        )
        assert del_resp.status_code == 204
        get_resp = await async_client.get(
            f"/api/v1/facturas/{fact_id}", headers=_auth(token)
        )
        assert get_resp.status_code == 404

    async def test_baja_factura_otro_tenant_404(self, async_client, fact_db):
        d = fact_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, FINANZAS_B_EMAIL)
        cr = await _crear(async_client, token_a, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        resp = await async_client.delete(
            f"/api/v1/facturas/{fact_id}", headers=_auth(token_b)
        )
        assert resp.status_code == 404


# ── TestFacturaEstado ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFacturaEstado:
    async def _mk(self, client: AsyncClient, token: str, docente_id) -> str:
        cr = await _crear(client, token, docente_id)
        assert cr.status_code == 201, cr.text
        return cr.json()["id"]

    async def test_cambiar_a_abonada_setea_abonada_at(self, async_client, fact_db):
        """Pendiente → Abonada: abonada_at se popula."""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        fact_id = await self._mk(async_client, token, fact_db["docente_fact_id"])
        resp = await async_client.post(
            f"/api/v1/facturas/{fact_id}/estado",
            headers=_auth(token),
            json={"estado": "Abonada"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["estado"] == "Abonada"
        assert body["abonada_at"] is not None

    async def test_cambiar_a_pendiente_limpia_abonada_at(self, async_client, fact_db):
        """Abonada → Pendiente: abonada_at vuelve a None."""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        fact_id = await self._mk(async_client, token, fact_db["docente_fact_id"])
        await async_client.post(
            f"/api/v1/facturas/{fact_id}/estado",
            headers=_auth(token),
            json={"estado": "Abonada"},
        )
        resp = await async_client.post(
            f"/api/v1/facturas/{fact_id}/estado",
            headers=_auth(token),
            json={"estado": "Pendiente"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["estado"] == "Pendiente"
        assert body["abonada_at"] is None

    async def test_estado_invalido_422(self, async_client, fact_db):
        """Un valor fuera del enum → 422 de Pydantic (no hay tercer estado)."""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        fact_id = await self._mk(async_client, token, fact_db["docente_fact_id"])
        resp = await async_client.post(
            f"/api/v1/facturas/{fact_id}/estado",
            headers=_auth(token),
            json={"estado": "Cancelada"},
        )
        assert resp.status_code == 422

    async def test_cambiar_estado_otro_tenant_404(self, async_client, fact_db):
        d = fact_db
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, FINANZAS_B_EMAIL)
        cr = await _crear(async_client, token_a, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        resp = await async_client.post(
            f"/api/v1/facturas/{fact_id}/estado",
            headers=_auth(token_b),
            json={"estado": "Abonada"},
        )
        assert resp.status_code == 404


# ── TestFacturaFiltros ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFacturaFiltros:
    async def test_filtro_usuario_id(self, async_client, fact_db):
        """Filtrar por usuario_id devuelve solo facturas de ese docente."""
        d = fact_db
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _crear(async_client, token, d["docente_fact_id"], detalle="D1")
        await _crear(async_client, token, d["docente_fact2_id"], detalle="D2")
        resp = await async_client.get(
            "/api/v1/facturas/",
            headers=_auth(token),
            params={"usuario_id": str(d["docente_fact_id"])},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["usuario_id"] == str(d["docente_fact_id"])

    async def test_filtro_estado(self, async_client, fact_db):
        """Filtrar por estado=Abonada devuelve solo las abonadas."""
        d = fact_db
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await _crear(async_client, token, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        await async_client.post(
            f"/api/v1/facturas/{fact_id}/estado",
            headers=_auth(token),
            json={"estado": "Abonada"},
        )
        await _crear(async_client, token, d["docente_fact_id"], detalle="Segunda Pendiente")
        resp = await async_client.get(
            "/api/v1/facturas/",
            headers=_auth(token),
            params={"estado": "Abonada"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert all(f["estado"] == "Abonada" for f in items)

    async def test_filtro_periodo(self, async_client, fact_db):
        """Filtrar por periodo retorna solo las facturas de ese período."""
        d = fact_db
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _crear(async_client, token, d["docente_fact_id"], periodo=PERIODO)
        await _crear(async_client, token, d["docente_fact_id"], periodo=PERIODO_2)
        resp = await async_client.get(
            "/api/v1/facturas/",
            headers=_auth(token),
            params={"periodo": PERIODO},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["periodo"] == PERIODO

    async def test_filtro_q_busqueda_en_detalle(self, async_client, fact_db):
        """Filtrar por q busca en el campo detalle (ILIKE)."""
        d = fact_db
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _crear(async_client, token, d["docente_fact_id"], detalle="Servicio de consultoria")
        await _crear(async_client, token, d["docente_fact_id"], periodo=PERIODO_2, detalle="Honorarios docentes")
        resp = await async_client.get(
            "/api/v1/facturas/",
            headers=_auth(token),
            params={"q": "consultoria"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert "consultoria" in items[0]["detalle"]

    async def test_filtro_fecha_desde_incluye_hoy(self, async_client, fact_db):
        """fecha_desde = hoy incluye una factura recién creada."""
        d = fact_db
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await _crear(async_client, token, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        today = datetime.date.today().isoformat()
        resp = await async_client.get(
            "/api/v1/facturas/",
            headers=_auth(token),
            params={"fecha_desde": today},
        )
        assert resp.status_code == 200
        ids = [f["id"] for f in resp.json()]
        assert fact_id in ids

    async def test_filtro_fecha_hasta_excluye_hoy(self, async_client, fact_db):
        """fecha_hasta = ayer excluye una factura creada hoy."""
        d = fact_db
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await _crear(async_client, token, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        resp = await async_client.get(
            "/api/v1/facturas/",
            headers=_auth(token),
            params={"fecha_hasta": yesterday},
        )
        assert resp.status_code == 200
        ids = [f["id"] for f in resp.json()]
        assert fact_id not in ids


# ── TestFacturaRBAC ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFacturaRBAC:
    async def test_profesor_listar_403(self, async_client, fact_db):
        """PROFESOR (sin facturas:gestionar) → 403 al listar."""
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.get("/api/v1/facturas/", headers=_auth(token))
        assert resp.status_code == 403

    async def test_profesor_crear_403(self, async_client, fact_db):
        """PROFESOR → 403 al intentar crear una factura."""
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await _crear(async_client, token, fact_db["docente_fact_id"])
        assert resp.status_code == 403

    async def test_profesor_cambiar_estado_403(self, async_client, fact_db):
        d = fact_db
        token_fin = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        cr = await _crear(async_client, token_fin, d["docente_fact_id"])
        fact_id = cr.json()["id"]
        token_prof = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.post(
            f"/api/v1/facturas/{fact_id}/estado",
            headers=_auth(token_prof),
            json={"estado": "Abonada"},
        )
        assert resp.status_code == 403

    async def test_sin_token_401_o_403(self, async_client, fact_db):
        resp = await async_client.get("/api/v1/facturas/")
        assert resp.status_code in (401, 403)
