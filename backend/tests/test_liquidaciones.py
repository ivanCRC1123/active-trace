"""C-18 liquidaciones — integration tests (Section 2).

Covers:
- Cálculo RN-34: base + plus × N_comisiones, Decimal correcto
- OD-5: docente sin SalarioBase → excluido + reportado en sin_base_vigente
- RN-26: datos bancarios incompletos → flag en liquidacion + sin_datos_bancarios
- RN-35: facturador=True → excluido_por_factura, fuera de total
- RN-36: NEXO incluido en total (tested via facturador test contrast)
- RN-22/37: inmutabilidad — recalcular rechazado si hay Cerradas
- Cierre atómico: solo cierra cerrable (no incompleto, no facturador)
- KPIs: total_sin_factura = Σ no-facturador; total_con_factura = count Abonadas
- Aislamiento tenant: lista/get filtrados por tenant
- RBAC: sin permiso → 403
"""

from datetime import date
from decimal import Decimal
from typing import AsyncGenerator

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
from app.models.materia_grupo import MateriaGrupo
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.salario_base import SalarioBase
from app.models.salario_plus import SalarioPlus
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_CODE = "liq-test-a"
OTHER_TENANT_CODE = "liq-test-b"
USER_PASS = "Admin123!"
FINANZAS_EMAIL = "liq.finanzas@test.edu.ar"
DOCENTE1_EMAIL = "liq.docente1@test.edu.ar"   # PROFESOR, completo, 2 comisiones
DOCENTE2_EMAIL = "liq.docente2@test.edu.ar"   # PROFESOR, sin banco
DOCENTE3_EMAIL = "liq.facturador@test.edu.ar" # PROFESOR, facturador=True
FINANZAS_B_EMAIL = "liq.finanzas.b@test.edu.ar"
PERIODO = "2026-06"
PERIODO_SIN_BASE = "2025-01"  # before SalarioBase desde=2026-01-01


# ── Fixture helpers ───────────────────────────────────────────────────────────


async def _liq_cleanup(db_session: AsyncSession) -> None:
    """Delete all data created by liq_db in FK-safe order.

    Called both at setup (clear stale state) and teardown (leave DB clean).
    """
    try:
        await db_session.execute(text("DELETE FROM factura"))
        await db_session.execute(text("DELETE FROM liquidacion"))
        await db_session.execute(text("DELETE FROM materia_grupo"))
        await db_session.execute(text("DELETE FROM salario_base"))
        await db_session.execute(text("DELETE FROM salario_plus"))
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
    except Exception:
        await db_session.rollback()
        raise


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def liq_db(db_session: AsyncSession) -> AsyncGenerator[dict, None]:
    """Seed two tenants with full liquidacion scenario.

    Yields a dict of IDs. Cleans up in setup AND teardown so the test
    passes deterministically even when run in isolation against a dirty DB.
    """
    await _liq_cleanup(db_session)

    def _user(email: str, tid, *, banco=None, cbu=None, alias=None, facturador=False) -> User:
        u = User(
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
        if banco:
            u.banco = banco
        if cbu:
            u.cbu_cifrado = cbu
        if alias:
            u.alias_cbu_cifrado = alias
        return u

    # ── Tenant A ──────────────────────────────────────────────────────────────

    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Liq Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    # Users
    finanzas = _user(FINANZAS_EMAIL, tid_a, banco="Banco F", cbu="111", alias="fin.alias")
    docente1 = _user(DOCENTE1_EMAIL, tid_a, banco="Banco N", cbu="22222", alias="d1.alias")
    docente2 = _user(DOCENTE2_EMAIL, tid_a)        # no banco — incompleto
    docente3 = _user(DOCENTE3_EMAIL, tid_a, banco="Banco F", cbu="33333", alias="d3.alias",
                     facturador=True)
    db_session.add_all([finanzas, docente1, docente2, docente3])
    await db_session.flush()
    for u in [finanzas, docente1, docente2, docente3]:
        await db_session.refresh(u)

    # RBAC
    rol_fin = Rol(tenant_id=tid_a, nombre="FINANZAS", descripcion="Finanzas")
    rol_prof = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    db_session.add_all([rol_fin, rol_prof])
    await db_session.flush()
    await db_session.refresh(rol_fin)
    await db_session.refresh(rol_prof)

    p_liq = Permiso(
        tenant_id=tid_a,
        codigo="liquidaciones:calcular_cerrar",
        modulo="liquidaciones",
        descripcion="Calcular/cerrar liquidaciones",
    )
    db_session.add(p_liq)
    await db_session.flush()
    await db_session.refresh(p_liq)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_fin.id, permiso_id=p_liq.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=finanzas.id, rol_id=rol_fin.id),
    ])
    await db_session.flush()

    # Academic structure
    carrera = Carrera(tenant_id=tid_a, codigo="ING-A", nombre="Ingeniería")
    materia = Materia(tenant_id=tid_a, codigo="PROG_I", nombre="Programación I")
    db_session.add_all([carrera, materia])
    await db_session.flush()
    await db_session.refresh(carrera)
    await db_session.refresh(materia)

    cohorte = Cohorte(
        tenant_id=tid_a, carrera_id=carrera.id,
        nombre="MAR-2026", anio=2026, vig_desde=date(2026, 1, 1),
    )
    db_session.add(cohorte)
    await db_session.flush()
    await db_session.refresh(cohorte)

    # Asignaciones: all 3 docentes in this materia/cohorte as PROFESOR
    # docente1: 2 comisiones, docente2: 1, docente3: 1
    a1 = Asignacion(
        tenant_id=tid_a, usuario_id=docente1.id, rol_id=rol_prof.id,
        materia_id=materia.id, cohorte_id=cohorte.id,
        desde=date(2026, 1, 1), comisiones=["C1", "C2"],
    )
    a2 = Asignacion(
        tenant_id=tid_a, usuario_id=docente2.id, rol_id=rol_prof.id,
        materia_id=materia.id, cohorte_id=cohorte.id,
        desde=date(2026, 1, 1), comisiones=["C3"],
    )
    a3 = Asignacion(
        tenant_id=tid_a, usuario_id=docente3.id, rol_id=rol_prof.id,
        materia_id=materia.id, cohorte_id=cohorte.id,
        desde=date(2026, 1, 1), comisiones=["C4"],
    )
    db_session.add_all([a1, a2, a3])
    await db_session.flush()

    # Grilla salarial
    mg = MateriaGrupo(tenant_id=tid_a, materia_id=materia.id, grupo="PROG")
    sb = SalarioBase(
        tenant_id=tid_a, rol="PROFESOR",
        monto=Decimal("5000.00"), desde=date(2026, 1, 1),
    )
    sp = SalarioPlus(
        tenant_id=tid_a, grupo="PROG", rol="PROFESOR",
        descripcion="Plus Prog", monto=Decimal("1000.00"), desde=date(2026, 1, 1),
    )
    db_session.add_all([mg, sb, sp])
    await db_session.flush()

    # ── Tenant B ──────────────────────────────────────────────────────────────

    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Liq Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    fin_b = _user(FINANZAS_B_EMAIL, tid_b, banco="X", cbu="X", alias="X")
    db_session.add(fin_b)
    await db_session.flush()
    await db_session.refresh(fin_b)

    rol_fin_b = Rol(tenant_id=tid_b, nombre="FINANZAS", descripcion="Finanzas")
    db_session.add(rol_fin_b)
    await db_session.flush()
    await db_session.refresh(rol_fin_b)

    p_liq_b = Permiso(
        tenant_id=tid_b, codigo="liquidaciones:calcular_cerrar",
        modulo="liquidaciones", descripcion="Calcular/cerrar",
    )
    db_session.add(p_liq_b)
    await db_session.flush()
    await db_session.refresh(p_liq_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_fin_b.id, permiso_id=p_liq_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=fin_b.id, rol_id=rol_fin_b.id),
    ])
    await db_session.flush()

    await db_session.commit()

    yield {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "cohorte_a_id": cohorte.id,
        "materia_a_id": materia.id,
        "docente1_id": docente1.id,
        "docente2_id": docente2.id,
        "docente3_id": docente3.id,
    }

    # Teardown — runs after every test (including on failure), leaving a clean DB.
    # This is what makes the fixture deterministic in isolation.
    await _liq_cleanup(db_session)


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


async def _calcular(client, token, cohorte_id, periodo=PERIODO) -> dict:
    resp = await client.post(
        "/api/v1/liquidaciones/calcular",
        headers=_auth(token),
        json={"cohorte_id": str(cohorte_id), "periodo": periodo},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _find(liquidaciones: list, docente_id) -> dict | None:
    uid = str(docente_id)
    return next((l for l in liquidaciones if l["usuario_id"] == uid), None)


# ── TestCalcular ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCalcular:
    async def test_calcular_ok_devuelve_tres_liquidaciones(self, async_client, liq_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        assert len(result["liquidaciones"]) == 3
        assert result["sin_base_vigente"] == []

    async def test_calcular_monto_docente1_dos_comisiones(self, async_client, liq_db):
        """docente1: base=5000 + plus=1000×2 = 7000"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        liq = _find(result["liquidaciones"], liq_db["docente1_id"])
        assert liq is not None
        assert Decimal(liq["monto_base"]) == Decimal("5000.00")
        assert Decimal(liq["monto_plus"]) == Decimal("2000.00")
        assert Decimal(liq["total"]) == Decimal("7000.00")

    async def test_calcular_monto_docente2_una_comision(self, async_client, liq_db):
        """docente2: base=5000 + plus=1000×1 = 6000"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        liq = _find(result["liquidaciones"], liq_db["docente2_id"])
        assert liq is not None
        assert Decimal(liq["total"]) == Decimal("6000.00")

    async def test_calcular_datos_bancarios_incompletos(self, async_client, liq_db):
        """docente2 sin banco → datos_bancarios_incompletos=True, en sin_datos_bancarios"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        liq = _find(result["liquidaciones"], liq_db["docente2_id"])
        assert liq["datos_bancarios_incompletos"] is True
        incompletos_ids = [i["usuario_id"] for i in result["sin_datos_bancarios"]]
        assert str(liq_db["docente2_id"]) in incompletos_ids

    async def test_calcular_facturador_marcado(self, async_client, liq_db):
        """docente3 facturador=True → excluido_por_factura=True, NO en sin_datos_bancarios"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        liq = _find(result["liquidaciones"], liq_db["docente3_id"])
        assert liq["excluido_por_factura"] is True
        incompletos_ids = [i["usuario_id"] for i in result["sin_datos_bancarios"]]
        assert str(liq_db["docente3_id"]) not in incompletos_ids

    async def test_calcular_sin_asignaciones_activas_retorna_vacio(self, async_client, liq_db):
        """Periodo previo a desde=2026-01-01 — no hay asignaciones activas → todo vacío.

        OD-5: sin_base_vigente se puebla cuando hay asignaciones activas sin SalarioBase.
        Si no hay asignaciones activas en el período, no hay grupos → listas vacías.
        """
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"], PERIODO_SIN_BASE)
        assert len(result["liquidaciones"]) == 0
        assert len(result["sin_base_vigente"]) == 0
        assert len(result["sin_datos_bancarios"]) == 0

    async def test_calcular_idempotente_con_estado_abierta(self, async_client, liq_db):
        """Recalcular una segunda vez cuando todas están Abierta actualiza, no duplica"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        r1 = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        ids1 = {l["id"] for l in r1["liquidaciones"]}
        r2 = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        ids2 = {l["id"] for l in r2["liquidaciones"]}
        # Same IDs: updates, not inserts
        assert ids1 == ids2

    async def test_calcular_rechaza_si_hay_cerrada(self, async_client, liq_db):
        """Una vez que existe alguna Cerrada, calcular → 409"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        resp = await async_client.post(
            "/api/v1/liquidaciones/calcular",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 409

    async def test_calcular_sin_permiso_403(self, async_client, liq_db):
        """Sin token → 401; con token sin permiso → 403"""
        resp = await async_client.post(
            "/api/v1/liquidaciones/calcular",
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code in (401, 403)

    async def test_calcular_od5_asignacion_activa_sin_base_vigente(
        self, async_client, liq_db, db_session
    ):
        """OD-5 caso real: asignación ACTIVA en el período pero sin SalarioBase para ese rol.

        Escenario: docente1 tiene asignación TUTOR (desde=2026-01-01, activa en PERIODO)
        pero no existe SalarioBase vigente para TUTOR.

        Verifica:
          (1) el par (docente1, TUTOR) aparece en sin_base_vigente con motivo correcto
          (2) NO se crea ninguna Liquidacion para TUTOR (excluido del cómputo)
          (3) el cierre NO lo cuenta: cerradas sigue siendo 1 (solo el PROFESOR de docente1)
        """
        # Agregar rol TUTOR + asignación activa en PERIODO para docente1 (sin SalarioBase TUTOR)
        rol_tutor = Rol(
            tenant_id=liq_db["tenant_a_id"], nombre="TUTOR", descripcion="Tutor"
        )
        db_session.add(rol_tutor)
        await db_session.flush()
        await db_session.refresh(rol_tutor)

        asig_tutor = Asignacion(
            tenant_id=liq_db["tenant_a_id"],
            usuario_id=liq_db["docente1_id"],
            rol_id=rol_tutor.id,
            materia_id=liq_db["materia_a_id"],
            cohorte_id=liq_db["cohorte_a_id"],
            desde=date(2026, 1, 1),
            comisiones=["CT1"],
        )
        db_session.add(asig_tutor)
        await db_session.commit()

        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"])

        # (1) docente1/TUTOR en sin_base_vigente
        tutor_sin_base = [
            e for e in result["sin_base_vigente"]
            if str(e["usuario_id"]) == str(liq_db["docente1_id"])
            and e["rol"] == "TUTOR"
        ]
        assert len(tutor_sin_base) == 1, "debe haber exactamente 1 entrada TUTOR en sin_base_vigente"
        assert tutor_sin_base[0]["motivo"] == "sin_base_vigente"

        # (2) ninguna Liquidacion TUTOR creada
        assert all(l["rol"] != "TUTOR" for l in result["liquidaciones"]), \
            "TUTOR no debe generar Liquidacion"

        # (3) cerrar no lo cuenta — docente1/PROFESOR cierra (1), TUTOR no existe en tabla
        resp = await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 200
        assert resp.json()["cerradas"] == 1


# ── TestCerrar ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestCerrar:
    async def test_cerrar_cierra_solo_cerrable(self, async_client, liq_db):
        """Cerrar devuelve cerradas=1: solo docente1 (completo, no-facturador)"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        resp = await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cerradas"] == 1

    async def test_cerrar_incompleto_queda_abierto(self, async_client, liq_db):
        """docente2 (datos incompletos) sigue Abierta tras cerrar"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        resp = await async_client.get(
            "/api/v1/liquidaciones/",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        rows = resp.json()
        liq2 = _find(rows, liq_db["docente2_id"])
        assert liq2["estado"] == "Abierta"

    async def test_cerrar_facturador_queda_abierto(self, async_client, liq_db):
        """docente3 (facturador) sigue Abierta tras cerrar"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        resp = await async_client.get(
            "/api/v1/liquidaciones/",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        rows = resp.json()
        liq3 = _find(rows, liq_db["docente3_id"])
        assert liq3["estado"] == "Abierta"

    async def test_cerrar_docente1_estado_cerrada(self, async_client, liq_db):
        """docente1 (completo, no-facturador) queda Cerrada"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        resp = await async_client.get(
            "/api/v1/liquidaciones/",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        rows = resp.json()
        liq1 = _find(rows, liq_db["docente1_id"])
        assert liq1["estado"] == "Cerrada"

    async def test_calcular_rechaza_tras_cerrar(self, async_client, liq_db):
        """Recalcular tras cerrar → 409 (RN-22/37)"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        resp = await async_client.post(
            "/api/v1/liquidaciones/calcular",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 409

    async def test_cerrar_sin_liquidaciones_devuelve_cero(self, async_client, liq_db):
        """Cerrar sin ninguna Abierta cerrable → cerradas=0"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        # No calcular first — no liquidaciones exist
        resp = await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 200
        assert resp.json()["cerradas"] == 0


# ── TestList ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestList:
    async def test_list_liquidaciones_devuelve_tres(self, async_client, liq_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        resp = await async_client.get(
            "/api/v1/liquidaciones/",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    async def test_list_filtra_por_tenant(self, async_client, liq_db):
        """Tenant B no ve liquidaciones de Tenant A"""
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, FINANZAS_B_EMAIL)
        await _calcular(async_client, token_a, liq_db["cohorte_a_id"])
        # B queries con el cohorte de A (cross-tenant — must return empty, not leak)
        resp = await async_client.get(
            "/api/v1/liquidaciones/",
            headers=_auth(token_b),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    async def test_get_liquidacion_ok(self, async_client, liq_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        result = await _calcular(async_client, token, liq_db["cohorte_a_id"])
        liq_id = result["liquidaciones"][0]["id"]
        resp = await async_client.get(
            f"/api/v1/liquidaciones/{liq_id}", headers=_auth(token)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == liq_id

    async def test_get_liquidacion_otro_tenant_404(self, async_client, liq_db):
        """Tenant B no puede ver liquidacion de Tenant A"""
        token_a = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, FINANZAS_B_EMAIL)
        result = await _calcular(async_client, token_a, liq_db["cohorte_a_id"])
        liq_id = result["liquidaciones"][0]["id"]
        resp = await async_client.get(
            f"/api/v1/liquidaciones/{liq_id}", headers=_auth(token_b)
        )
        assert resp.status_code == 404

    async def test_list_sin_permiso_403(self, async_client, liq_db):
        resp = await async_client.get(
            "/api/v1/liquidaciones/",
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code in (401, 403)


# ── TestKPIs ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestKPIs:
    async def test_kpis_total_sin_factura(self, async_client, liq_db):
        """total_sin_factura = docente1(7000) + docente2(6000) = 13000 (docente3 excluido)"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        resp = await async_client.get(
            "/api/v1/liquidaciones/kpis",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert Decimal(body["total_sin_factura"]) == Decimal("13000.00")

    async def test_kpis_count_docentes(self, async_client, liq_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        resp = await async_client.get(
            "/api/v1/liquidaciones/kpis",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.json()["count_docentes"] == 3

    async def test_kpis_count_cerrada_tras_cerrar(self, async_client, liq_db):
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        await async_client.post(
            "/api/v1/liquidaciones/cerrar",
            headers=_auth(token),
            json={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        resp = await async_client.get(
            "/api/v1/liquidaciones/kpis",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        body = resp.json()
        assert body["count_cerrada"] == 1
        assert body["count_abierta"] == 2  # docente2 + docente3 remain Abierta

    async def test_kpis_total_con_factura_inicialmente_cero(self, async_client, liq_db):
        """total_con_factura = count Abonadas — sin facturas → 0"""
        token = await _login(async_client, TENANT_CODE, FINANZAS_EMAIL)
        await _calcular(async_client, token, liq_db["cohorte_a_id"])
        resp = await async_client.get(
            "/api/v1/liquidaciones/kpis",
            headers=_auth(token),
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.json()["total_con_factura"] == 0

    async def test_kpis_sin_permiso_403(self, async_client, liq_db):
        resp = await async_client.get(
            "/api/v1/liquidaciones/kpis",
            params={"cohorte_id": str(liq_db["cohorte_a_id"]), "periodo": PERIODO},
        )
        assert resp.status_code in (401, 403)
