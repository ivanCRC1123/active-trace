"""C-11 analisis-atrasados-reportes — integration tests.

Fixture scenario (4 students, 3 activities):
  Activities:  "TP1" (numerica), "TP2" (numerica), "Foro" (textual)
  al_dia:          TP1=80✓  TP2=75✓  Foro="Satisfactorio"✓   → 3/3 aprobadas
  bajo_umbral:     TP1=30✗  TP2=80✓  Foro="Satisfactorio"✓   → bajo_umbral TP1
  faltante:        (sin calificaciones)                        → faltante TP1+TP2+Foro
  sin_corregir:    TP1=70✓  TP2=70✓  Foro faltante + fin=True → sin_corregir (no atrasado)

Expected:
  atrasados      → bajo_umbral (bajo_umbral TP1), faltante (faltante TP1+TP2+Foro)
  ranking        → al_dia(3), bajo_umbral(2), sin_corregir(2); faltante excluded (0 aprobadas)
  notas_finales  → al_dia 100%, bajo_umbral 66.67%, sin_corregir 100%, faltante None
  sin_corregir   → sin_corregir alumno, actividad "Foro"
  monitor        → bajo_umbral + faltante "atrasado", al_dia + sin_corregir "al_dia"
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password
from app.models.asignacion import Asignacion
from app.models.calificacion import Calificacion, OrigenCalificacion
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.entrada_padron import EntradaPadron
from app.models.finalizacion_actividad import FinalizacionActividad
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol
from app.models.version_padron import VersionPadron

# ── Constants ─────────────────────────────────────────────────────────────────

TENANT_CODE = "analisis-test"
USER_PASS = "Admin123!"
PROF_EMAIL  = "an.prof@test.edu.ar"
COORD_EMAIL = "an.coord@test.edu.ar"
NOPERM_EMAIL = "an.noperm@test.edu.ar"

AL_DIA_EMAIL        = "al_dia@alumnos.edu"
BAJO_UMBRAL_EMAIL   = "bajo_umbral@alumnos.edu"
FALTANTE_EMAIL      = "faltante@alumnos.edu"
SIN_CORREGIR_EMAIL  = "sin_corregir@alumnos.edu"

ACT_TP1  = "TP1"
ACT_TP2  = "TP2"
ACT_FORO = "Foro"

UMBRAL_PCT = 60


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user(email: str, tid) -> User:
    return User(
        email_cifrado=encrypt(email),
        email_hash=hmac_email(email),
        password_hash=hash_password(USER_PASS),
        nombre="Test", apellidos="User",
        is_active=True, is_2fa_enabled=False,
        tenant_id=tid,
    )


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": TENANT_CODE, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cal(
    tid, asig_id, ep_id, materia_id, actividad: str,
    nota_num: float | None = None, nota_txt: str | None = None,
    aprobado: bool = False,
) -> Calificacion:
    c = Calificacion(
        tenant_id=tid,
        asignacion_id=asig_id,
        entrada_padron_id=ep_id,
        materia_id=materia_id,
        actividad=actividad,
        aprobado=aprobado,
        origen=OrigenCalificacion.Importado,
    )
    if nota_num is not None:
        c.nota_numerica = Decimal(str(nota_num))
    if nota_txt is not None:
        c.nota_textual = nota_txt
    return c


def _fin(tid, asig_id, ep_id, materia_id, actividad: str, finalizado: bool) -> FinalizacionActividad:
    return FinalizacionActividad(
        tenant_id=tid,
        asignacion_id=asig_id,
        entrada_padron_id=ep_id,
        materia_id=materia_id,
        actividad=actividad,
        finalizado=finalizado,
    )


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def analisis_db(db_session: AsyncSession) -> dict:
    """Seed full analisis scenario.

    Returns dict with IDs for use in tests.
    """
    # --- clean slate ---
    for tbl in (
        "finalizacion_actividad", "calificacion", "umbral_materia",
        "entrada_padron", "version_padron", "asignacion",
        "audit_log", "cohorte", "materia", "carrera",
        "user_rol", "rol_permiso", "permiso", "rol",
        "refresh_token", "recovery_token", '"user"', "tenant",
    ):
        await db_session.execute(text(f"DELETE FROM {tbl}"))
    await db_session.commit()

    # --- tenant ---
    tenant = Tenant(codigo=TENANT_CODE, nombre="Analisis Test")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    tid = tenant.id

    # --- users ---
    prof    = _user(PROF_EMAIL, tid)
    coord   = _user(COORD_EMAIL, tid)
    noperm  = _user(NOPERM_EMAIL, tid)
    db_session.add_all([prof, coord, noperm])
    await db_session.flush()
    for u in (prof, coord, noperm):
        await db_session.refresh(u)

    # --- roles ---
    rol_prof   = Rol(tenant_id=tid, nombre="PROFESOR",     descripcion="Profesor")
    rol_coord  = Rol(tenant_id=tid, nombre="COORDINADOR",  descripcion="Coordinador")
    rol_noperm = Rol(tenant_id=tid, nombre="NEXO",         descripcion="Sin permisos")
    db_session.add_all([rol_prof, rol_coord, rol_noperm])
    await db_session.flush()
    for r in (rol_prof, rol_coord, rol_noperm):
        await db_session.refresh(r)

    # --- permissions ---
    p_importar = Permiso(tenant_id=tid, codigo="calificaciones:importar",          modulo="calificaciones", descripcion="Importar")
    p_ver      = Permiso(tenant_id=tid, codigo="atrasados:ver",                    modulo="atrasados",      descripcion="Ver atrasados")
    p_sc       = Permiso(tenant_id=tid, codigo="entregas:detectar_sin_corregir",   modulo="entregas",       descripcion="Sin corregir")
    db_session.add_all([p_importar, p_ver, p_sc])
    await db_session.flush()
    for p in (p_importar, p_ver, p_sc):
        await db_session.refresh(p)

    db_session.add_all([
        # COORDINADOR scope=all
        RolPermiso(tenant_id=tid, rol_id=rol_coord.id, permiso_id=p_importar.id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_coord.id, permiso_id=p_ver.id,      scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_coord.id, permiso_id=p_sc.id,       scope="all"),
        # PROFESOR scope=own
        RolPermiso(tenant_id=tid, rol_id=rol_prof.id, permiso_id=p_importar.id, scope="own"),
        RolPermiso(tenant_id=tid, rol_id=rol_prof.id, permiso_id=p_ver.id,      scope="own"),
        RolPermiso(tenant_id=tid, rol_id=rol_prof.id, permiso_id=p_sc.id,       scope="own"),
        # user → rol
        UserRol(tenant_id=tid, user_id=prof.id,   rol_id=rol_prof.id),
        UserRol(tenant_id=tid, user_id=coord.id,  rol_id=rol_coord.id),
        UserRol(tenant_id=tid, user_id=noperm.id, rol_id=rol_noperm.id),
    ])
    await db_session.flush()

    # --- academic structure ---
    carrera = Carrera(tenant_id=tid, codigo="CAR", nombre="Carrera Test", estado="Activa")
    db_session.add(carrera)
    await db_session.flush()
    await db_session.refresh(carrera)

    cohorte = Cohorte(
        tenant_id=tid, carrera_id=carrera.id, nombre="MAR-2026",
        anio=2026, vig_desde=date(2026, 3, 1), estado="Activa",
    )
    db_session.add(cohorte)
    await db_session.flush()
    await db_session.refresh(cohorte)

    materia = Materia(tenant_id=tid, codigo="MAT1", nombre="Materia 1", estado="Activa")
    db_session.add(materia)
    await db_session.flush()
    await db_session.refresh(materia)

    mid = materia.id
    cid = cohorte.id

    # --- asignaciones ---
    asig_prof = Asignacion(
        tenant_id=tid, usuario_id=prof.id, rol_id=rol_prof.id,
        materia_id=mid, cohorte_id=cid, carrera_id=carrera.id,
        desde=date(2026, 3, 1),
    )
    asig_coord = Asignacion(
        tenant_id=tid, usuario_id=coord.id, rol_id=rol_coord.id,
        materia_id=mid, cohorte_id=cid, carrera_id=carrera.id,
        desde=date(2026, 3, 1),
    )
    db_session.add_all([asig_prof, asig_coord])
    await db_session.flush()
    for a in (asig_prof, asig_coord):
        await db_session.refresh(a)

    # --- padron ---
    version = VersionPadron(
        tenant_id=tid, materia_id=mid, cohorte_id=cid,
        cargado_por=prof.id, activa=True,
    )
    db_session.add(version)
    await db_session.flush()
    await db_session.refresh(version)
    vid = version.id

    def _ep(email: str, nombre: str) -> EntradaPadron:
        return EntradaPadron(
            tenant_id=tid, version_id=vid,
            nombre=nombre, apellidos="Apellido",
            email_cifrado=encrypt(email),
            email_hash=hmac_email(email),
        )

    ep_al_dia       = _ep(AL_DIA_EMAIL,       "AlDia")
    ep_bajo_umbral  = _ep(BAJO_UMBRAL_EMAIL,  "BajoUmbral")
    ep_faltante     = _ep(FALTANTE_EMAIL,     "Faltante")
    ep_sin_corregir = _ep(SIN_CORREGIR_EMAIL, "SinCorregir")
    db_session.add_all([ep_al_dia, ep_bajo_umbral, ep_faltante, ep_sin_corregir])
    await db_session.flush()
    for ep in (ep_al_dia, ep_bajo_umbral, ep_faltante, ep_sin_corregir):
        await db_session.refresh(ep)

    aid = asig_prof.id

    # --- calificaciones ---
    # al_dia:       TP1✓ TP2✓ Foro✓
    # bajo_umbral:  TP1✗ TP2✓ Foro✓
    # faltante:     (ninguna) → faltante para TP1, TP2, Foro
    # sin_corregir: TP1✓ TP2✓, Foro faltante + finalizado=True → sin_corregir, NO faltante
    calificaciones = [
        _cal(tid, aid, ep_al_dia.id,      mid, ACT_TP1,  nota_num=80, aprobado=True),
        _cal(tid, aid, ep_al_dia.id,      mid, ACT_TP2,  nota_num=75, aprobado=True),
        _cal(tid, aid, ep_al_dia.id,      mid, ACT_FORO, nota_txt="Satisfactorio", aprobado=True),
        _cal(tid, aid, ep_bajo_umbral.id, mid, ACT_TP1,  nota_num=30, aprobado=False),
        _cal(tid, aid, ep_bajo_umbral.id, mid, ACT_TP2,  nota_num=80, aprobado=True),
        _cal(tid, aid, ep_bajo_umbral.id, mid, ACT_FORO, nota_txt="Satisfactorio", aprobado=True),
        # faltante: no calificaciones
        _cal(tid, aid, ep_sin_corregir.id, mid, ACT_TP1, nota_num=70, aprobado=True),
        _cal(tid, aid, ep_sin_corregir.id, mid, ACT_TP2, nota_num=70, aprobado=True),
        # sin_corregir: Foro missing, will be covered by finalizacion below
    ]
    db_session.add_all(calificaciones)
    await db_session.flush()

    # --- finalizacion: sin_corregir finalizó Foro pero no tiene nota → sin corregir ---
    fin = _fin(tid, aid, ep_sin_corregir.id, mid, ACT_FORO, finalizado=True)
    db_session.add(fin)
    await db_session.commit()

    return {
        "tenant_id":   str(tid),
        "materia_id":  str(mid),
        "cohorte_id":  str(cid),
        "asig_prof_id":  str(asig_prof.id),
        "asig_coord_id": str(asig_coord.id),
        "ep_al_dia_id":       str(ep_al_dia.id),
        "ep_bajo_umbral_id":  str(ep_bajo_umbral.id),
        "ep_faltante_id":     str(ep_faltante.id),
        "ep_sin_corregir_id": str(ep_sin_corregir.id),
        "version_id": str(vid),
    }


# ── AN-01: atrasados ──────────────────────────────────────────────────────────

class TestAtrasados:
    @pytest.mark.asyncio
    async def test_atrasados_bajo_umbral_incluido(self, analisis_db, async_client, app):
        """bajo_umbral tiene TP1 no aprobado → aparece en atrasados."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        ep_ids = [a["entrada_padron_id"] for a in resp.json()["atrasados"]]
        assert analisis_db["ep_bajo_umbral_id"] in ep_ids

    @pytest.mark.asyncio
    async def test_atrasados_faltante_incluido(self, analisis_db, async_client, app):
        """faltante no tiene TP1 ni Foro → aparece en atrasados."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        ep_ids = [a["entrada_padron_id"] for a in resp.json()["atrasados"]]
        assert analisis_db["ep_faltante_id"] in ep_ids

    @pytest.mark.asyncio
    async def test_atrasados_al_dia_excluido(self, analisis_db, async_client, app):
        """al_dia tiene todo aprobado → NO aparece en atrasados."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        ep_ids = [a["entrada_padron_id"] for a in resp.json()["atrasados"]]
        assert analisis_db["ep_al_dia_id"] not in ep_ids

    @pytest.mark.asyncio
    async def test_atrasados_sin_corregir_excluido(self, analisis_db, async_client, app):
        """sin_corregir tiene Foro finalizado=True pero sin nota → NO es faltante (D-C11-3)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        ep_ids = [a["entrada_padron_id"] for a in resp.json()["atrasados"]]
        assert analisis_db["ep_sin_corregir_id"] not in ep_ids

    @pytest.mark.asyncio
    async def test_atrasados_total_alumnos_correcto(self, analisis_db, async_client, app):
        """total_alumnos refleja el padrón activo completo (4 estudiantes)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_alumnos"] == 4
        assert body["total_atrasados"] == 2

    @pytest.mark.asyncio
    async def test_atrasados_bajo_umbral_actividades(self, analisis_db, async_client, app):
        """bajo_umbral tiene TP1 en actividades_bajo_umbral y nada en faltantes."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        body = resp.json()
        alumno = next(
            a for a in body["atrasados"]
            if a["entrada_padron_id"] == analisis_db["ep_bajo_umbral_id"]
        )
        assert ACT_TP1 in alumno["actividades_bajo_umbral"]
        assert alumno["actividades_faltantes"] == []  # tiene TP1, TP2 y Foro calificados

    @pytest.mark.asyncio
    async def test_atrasados_403_sin_permiso(self, analisis_db, async_client, app):
        """Usuario sin permiso atrasados:ver recibe 403."""
        token = await _login(async_client, NOPERM_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_atrasados_coord_scope_all(self, analisis_db, async_client, app):
        """COORDINADOR con scope=all ve los mismos atrasados."""
        token = await _login(async_client, COORD_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/atrasados",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total_atrasados"] == 2


# ── AN-02: ranking ────────────────────────────────────────────────────────────

class TestRanking:
    @pytest.mark.asyncio
    async def test_ranking_faltante_excluido_rn09(self, analisis_db, async_client, app):
        """faltante tiene 0 aprobadas → excluido del ranking (RN-09)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/ranking",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        ep_ids = [i["entrada_padron_id"] for i in resp.json()["items"]]
        assert analisis_db["ep_faltante_id"] not in ep_ids

    @pytest.mark.asyncio
    async def test_ranking_totales(self, analisis_db, async_client, app):
        """3 incluidos (al_dia, bajo_umbral, sin_corregir), 1 excluido (faltante)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/ranking",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_incluidos"] == 3
        assert body["total_excluidos"] == 1

    @pytest.mark.asyncio
    async def test_ranking_al_dia_primero(self, analisis_db, async_client, app):
        """al_dia tiene 3 aprobadas → posición 1."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/ranking",
            headers=_auth(token),
        )
        body = resp.json()
        primero = body["items"][0]
        assert primero["entrada_padron_id"] == analisis_db["ep_al_dia_id"]
        assert primero["posicion"] == 1
        assert primero["total_aprobadas"] == 3

    @pytest.mark.asyncio
    async def test_ranking_posiciones_correlativas(self, analisis_db, async_client, app):
        """Posiciones son 1-indexed y correlativas."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/ranking",
            headers=_auth(token),
        )
        posiciones = [i["posicion"] for i in resp.json()["items"]]
        assert posiciones == list(range(1, len(posiciones) + 1))

    @pytest.mark.asyncio
    async def test_ranking_403_sin_permiso(self, analisis_db, async_client, app):
        """Usuario sin permiso recibe 403."""
        token = await _login(async_client, NOPERM_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/ranking",
            headers=_auth(token),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_ranking_coord_scope_all(self, analisis_db, async_client, app):
        """COORDINADOR scope=all ve el mismo ranking."""
        token = await _login(async_client, COORD_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/ranking",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total_incluidos"] == 3


# ── AN-03: reporte rápido ─────────────────────────────────────────────────────

class TestReporteRapido:
    @pytest.mark.asyncio
    async def test_reporte_rapido_tiene_datos(self, analisis_db, async_client, app):
        """Reporte indica tiene_datos=True cuando hay calificaciones."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/reportes-rapidos",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tiene_datos"] is True
        assert body["total_alumnos"] == 4

    @pytest.mark.asyncio
    async def test_reporte_rapido_actividades(self, analisis_db, async_client, app):
        """Detecta 3 actividades distintas (TP1, TP2, Foro)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/reportes-rapidos",
            headers=_auth(token),
        )
        assert resp.json()["total_actividades"] == 3

    @pytest.mark.asyncio
    async def test_reporte_rapido_alumnos_atrasados(self, analisis_db, async_client, app):
        """alumnos_atrasados coincide con count de atrasados (2)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/reportes-rapidos",
            headers=_auth(token),
        )
        assert resp.json()["alumnos_atrasados"] == 2

    @pytest.mark.asyncio
    async def test_reporte_rapido_403(self, analisis_db, async_client, app):
        token = await _login(async_client, NOPERM_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/reportes-rapidos",
            headers=_auth(token),
        )
        assert resp.status_code == 403


# ── AN-04: notas finales ──────────────────────────────────────────────────────

class TestNotasFinales:
    @pytest.mark.asyncio
    async def test_notas_finales_todos_los_alumnos(self, analisis_db, async_client, app):
        """Devuelve los 4 alumnos del padrón."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total_alumnos"] == 4

    @pytest.mark.asyncio
    async def test_notas_finales_al_dia_100_pct(self, analisis_db, async_client, app):
        """al_dia tiene 3/3 aprobadas → pct_actividades_aprobadas == 100.0."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales",
            headers=_auth(token),
        )
        items = resp.json()["items"]
        alumno = next(i for i in items if i["entrada_padron_id"] == analisis_db["ep_al_dia_id"])
        assert alumno["pct_actividades_aprobadas"] == 100.0
        assert alumno["aprobadas"] == 3

    @pytest.mark.asyncio
    async def test_notas_finales_bajo_umbral_pct(self, analisis_db, async_client, app):
        """bajo_umbral tiene 2/3 aprobadas → pct ≈ 66.67."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales",
            headers=_auth(token),
        )
        items = resp.json()["items"]
        alumno = next(i for i in items if i["entrada_padron_id"] == analisis_db["ep_bajo_umbral_id"])
        assert alumno["aprobadas"] == 2
        assert alumno["total_calificaciones"] == 3
        assert abs(alumno["pct_actividades_aprobadas"] - 66.67) < 0.01

    @pytest.mark.asyncio
    async def test_notas_finales_faltante_pct_none(self, analisis_db, async_client, app):
        """faltante no tiene calificaciones → pct_actividades_aprobadas es None."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales",
            headers=_auth(token),
        )
        items = resp.json()["items"]
        alumno = next(i for i in items if i["entrada_padron_id"] == analisis_db["ep_faltante_id"])
        assert alumno["pct_actividades_aprobadas"] is None
        assert alumno["total_calificaciones"] == 0

    @pytest.mark.asyncio
    async def test_notas_finales_exportar_csv(self, analisis_db, async_client, app):
        """Exportar devuelve text/csv con cabecera correcta."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales/exportar",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().splitlines()
        assert lines[0].startswith("apellidos,nombre")
        assert len(lines) == 5  # header + 4 alumnos

    @pytest.mark.asyncio
    async def test_notas_finales_403(self, analisis_db, async_client, app):
        token = await _login(async_client, NOPERM_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/notas-finales",
            headers=_auth(token),
        )
        assert resp.status_code == 403


# ── AN-05: importar finalizacion ──────────────────────────────────────────────

import csv as _csv
import io as _io


def _fin_csv(rows: list[tuple[str, str]]) -> bytes:
    """Build a minimal finalizacion CSV: email + Foro column."""
    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(["email", ACT_FORO])
    for email, valor in rows:
        writer.writerow([email, valor])
    return buf.getvalue().encode("utf-8")


class TestImportarFinalizacion:
    @pytest.mark.asyncio
    async def test_importar_happy_path(self, analisis_db, async_client, app):
        """Import CSV resuelve emails → entradas_procesadas y finalizadas."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        content = _fin_csv([
            (AL_DIA_EMAIL,       "completado"),
            (BAJO_UMBRAL_EMAIL,  "no"),
            (SIN_CORREGIR_EMAIL, "completado"),
        ])
        resp = await async_client.post(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/importar-finalizacion",
            headers=_auth(token),
            files={"file": ("fin.csv", content, "text/csv")},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["entradas_procesadas"] == 3
        assert body["finalizadas"] == 2          # al_dia + sin_corregir
        assert body["no_vinculadas"] == 0
        assert body["actividades_detectadas"] == 1

    @pytest.mark.asyncio
    async def test_importar_email_no_vinculado(self, analisis_db, async_client, app):
        """Email que no está en el padrón suma a no_vinculadas."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        content = _fin_csv([
            (AL_DIA_EMAIL,          "completado"),
            ("fantasma@test.com",   "completado"),
        ])
        resp = await async_client.post(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/importar-finalizacion",
            headers=_auth(token),
            files={"file": ("fin.csv", content, "text/csv")},
        )
        assert resp.status_code == 201
        assert resp.json()["no_vinculadas"] == 1

    @pytest.mark.asyncio
    async def test_importar_destructivo_reemplaza(self, analisis_db, async_client, app):
        """Segunda importación reemplaza la anterior (D-C11-2)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]

        content1 = _fin_csv([(AL_DIA_EMAIL, "completado"), (BAJO_UMBRAL_EMAIL, "completado")])
        await async_client.post(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/importar-finalizacion",
            headers=_auth(token),
            files={"file": ("fin.csv", content1, "text/csv")},
        )
        content2 = _fin_csv([(FALTANTE_EMAIL, "completado")])
        resp = await async_client.post(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/importar-finalizacion",
            headers=_auth(token),
            files={"file": ("fin.csv", content2, "text/csv")},
        )
        assert resp.status_code == 201
        assert resp.json()["entradas_procesadas"] == 1

    @pytest.mark.asyncio
    async def test_importar_403_sin_permiso(self, analisis_db, async_client, app):
        token = await _login(async_client, NOPERM_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        content = _fin_csv([(AL_DIA_EMAIL, "completado")])
        resp = await async_client.post(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/importar-finalizacion",
            headers=_auth(token),
            files={"file": ("fin.csv", content, "text/csv")},
        )
        assert resp.status_code == 403


# ── AN-06: sin corregir ───────────────────────────────────────────────────────

class TestSinCorregir:
    @pytest.mark.asyncio
    async def test_sin_corregir_detecta_alumno(self, analisis_db, async_client, app):
        """sin_corregir tiene Foro finalizado=True sin nota → aparece en lista."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/sin-corregir",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        ep_ids = [i["entrada_padron_id"] for i in body["items"]]
        assert analisis_db["ep_sin_corregir_id"] in ep_ids

    @pytest.mark.asyncio
    async def test_sin_corregir_actividad_correcta(self, analisis_db, async_client, app):
        """La actividad reportada es 'Foro' (la textual sin calificacion)."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/sin-corregir",
            headers=_auth(token),
        )
        item = next(
            i for i in resp.json()["items"]
            if i["entrada_padron_id"] == analisis_db["ep_sin_corregir_id"]
        )
        assert item["actividad"] == ACT_FORO

    @pytest.mark.asyncio
    async def test_sin_corregir_al_dia_no_incluido(self, analisis_db, async_client, app):
        """al_dia tiene Foro con nota → no aparece en sin_corregir."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/sin-corregir",
            headers=_auth(token),
        )
        ep_ids = [i["entrada_padron_id"] for i in resp.json()["items"]]
        assert analisis_db["ep_al_dia_id"] not in ep_ids

    @pytest.mark.asyncio
    async def test_sin_corregir_exportar_csv(self, analisis_db, async_client, app):
        """Exportar devuelve text/csv con cabecera y al menos 1 fila de datos."""
        token = await _login(async_client, PROF_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/sin-corregir/exportar",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().splitlines()
        assert lines[0] == "apellidos,nombre,comision,actividad"
        assert len(lines) >= 2

    @pytest.mark.asyncio
    async def test_sin_corregir_403(self, analisis_db, async_client, app):
        token = await _login(async_client, NOPERM_EMAIL)
        mid, cid = analisis_db["materia_id"], analisis_db["cohorte_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/{mid}/cohortes/{cid}/sin-corregir",
            headers=_auth(token),
        )
        assert resp.status_code == 403


# ── AN-07: monitor ────────────────────────────────────────────────────────────

class TestMonitor:
    @pytest.mark.asyncio
    async def test_monitor_devuelve_todos_los_alumnos(self, analisis_db, async_client, app):
        """Sin filtros devuelve los 4 alumnos del padrón activo."""
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/analisis/monitor",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 4
        assert len(body["items"]) == 4

    @pytest.mark.asyncio
    async def test_monitor_estado_atrasado(self, analisis_db, async_client, app):
        """Filtrando por estado=atrasado devuelve 2 (bajo_umbral + faltante)."""
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/analisis/monitor?estado=atrasado",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert all(i["estado"] == "atrasado" for i in body["items"])
        ep_ids = {i["entrada_padron_id"] for i in body["items"]}
        assert analisis_db["ep_bajo_umbral_id"] in ep_ids
        assert analisis_db["ep_faltante_id"] in ep_ids

    @pytest.mark.asyncio
    async def test_monitor_estado_al_dia(self, analisis_db, async_client, app):
        """Filtrando por estado=al_dia devuelve al_dia y sin_corregir."""
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/analisis/monitor?estado=al_dia",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        ep_ids = {i["entrada_padron_id"] for i in resp.json()["items"]}
        assert analisis_db["ep_al_dia_id"] in ep_ids
        assert analisis_db["ep_sin_corregir_id"] in ep_ids

    @pytest.mark.asyncio
    async def test_monitor_paginacion(self, analisis_db, async_client, app):
        """limit y offset funcionan correctamente."""
        token = await _login(async_client, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/analisis/monitor?limit=2&offset=0",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["limit"] == 2
        assert body["offset"] == 0
        assert body["total"] == 4

    @pytest.mark.asyncio
    async def test_monitor_filtro_materia(self, analisis_db, async_client, app):
        """Filtrando por materia_id devuelve sólo alumnos de esa materia."""
        token = await _login(async_client, COORD_EMAIL)
        mid = analisis_db["materia_id"]
        resp = await async_client.get(
            f"/api/v1/analisis/monitor?materia_id={mid}",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 4

    @pytest.mark.asyncio
    async def test_monitor_403_sin_permiso(self, analisis_db, async_client, app):
        token = await _login(async_client, NOPERM_EMAIL)
        resp = await async_client.get(
            "/api/v1/analisis/monitor",
            headers=_auth(token),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_monitor_prof_scope_own(self, analisis_db, async_client, app):
        """PROFESOR scope=own ve sólo los alumnos de su asignación."""
        token = await _login(async_client, PROF_EMAIL)
        resp = await async_client.get(
            "/api/v1/analisis/monitor",
            headers=_auth(token),
        )
        assert resp.status_code == 200
        # PROFESOR ve todos los alumnos que tienen calificaciones de su asignacion
        # (3 estudiantes tienen calificaciones: al_dia, bajo_umbral, sin_corregir)
        body = resp.json()
        ep_ids = {i["entrada_padron_id"] for i in body["items"]}
        assert analisis_db["ep_al_dia_id"] in ep_ids
        assert analisis_db["ep_bajo_umbral_id"] in ep_ids
        assert analisis_db["ep_sin_corregir_id"] in ep_ids
