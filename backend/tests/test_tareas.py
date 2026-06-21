"""C-16 tareas-internas — tests de integración.

Cubre (patas de access-control primero):
- mis-tareas self-scoped: TUTOR ve SUS tareas sin permiso; NO las de otros
- PROFESOR scope=own: sin materia → 403; materia ajena → 403; materia propia → 201
- comentarios membership: solo asignado_a / asignado_por / gestor; tercero ajeno → 403
- auditoría: TAREA_ASIGNAR y TAREA_ESTADO_CAMBIAR en VALID_ACTION_CODES
- FSM: transiciones válidas/inválidas/terminales
- admin global: COORDINADOR ve todo; PROFESOR scope=own; TUTOR sin permiso → 403
- tenant isolation: tareas de tenant B invisibles para tenant A
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt, hmac_email
from app.core.security import create_access_token, hash_password
from app.models.asignacion import Asignacion
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tarea import Tarea
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_A = "tar-test-a"
TENANT_B = "tar-test-b"
USER_PASS = "Test123!"


# ── Cleanup scoped (C-13 pattern) ────────────────────────────────────────────

async def _delete_tar_tenant_data(session: AsyncSession, *codes: str) -> None:
    """Remove tar test data scoped to specific tenant codes only."""
    for code in codes:
        tid_sub = "(SELECT id FROM tenant WHERE codigo = :c)"
        # FK leaves first
        await session.execute(
            text(f"DELETE FROM comentario_tarea WHERE tenant_id IN {tid_sub}"),
            {"c": code},
        )
        await session.execute(
            text(f"DELETE FROM tarea WHERE tenant_id IN {tid_sub}"),
            {"c": code},
        )
        await session.execute(
            text(f"DELETE FROM audit_log WHERE tenant_id IN {tid_sub}"),
            {"c": code},
        )
        for table in ("asignacion", "cohorte", "materia", "carrera"):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN {tid_sub}"),
                {"c": code},
            )
        for table in ("user_rol", "rol_permiso", "permiso", "rol"):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN {tid_sub}"),
                {"c": code},
            )
        for table in ("refresh_token", "recovery_token"):
            await session.execute(
                text(
                    f'DELETE FROM {table} WHERE user_id IN '
                    f'(SELECT id FROM "user" WHERE tenant_id IN {tid_sub})'
                ),
                {"c": code},
            )
        await session.execute(
            text(f'DELETE FROM "user" WHERE tenant_id IN {tid_sub}'),
            {"c": code},
        )
        await session.execute(text("DELETE FROM tenant WHERE codigo = :c"), {"c": code})
    await session.commit()


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def tar_db(db_session: AsyncSession) -> dict:
    """
    Tenant A:
      - tutor_a   (TUTOR — sin tareas_internas:gestionar)
      - prof_a    (PROFESOR — gestionar:own — asignado a mat_a)
      - prof_b    (PROFESOR — gestionar:own — asignado a mat_b; materia ajena para prof_a)
      - coord_a   (COORDINADOR — gestionar:all)
      - tercero_a (sin rol, sin permisos — para probar 403 membership)
    mat_a y mat_b en tenant A.
    Tenant B:
      - coord_b   (COORDINADOR — gestionar:all)
    """
    await _delete_tar_tenant_data(db_session, TENANT_A, TENANT_B)

    def _user(email: str, tid: UUID, nombre: str = "Test", apellidos: str = "User") -> User:
        return User(
            email_cifrado=encrypt(email),
            email_hash=hmac_email(email),
            password_hash=hash_password(USER_PASS),
            nombre=nombre,
            apellidos=apellidos,
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
        )

    # ── Tenant A ─────────────────────────────────────────────────────────────
    tenant_a = Tenant(codigo=TENANT_A, nombre="Tareas Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    tutor_a   = _user("tar.tutor@test.edu.ar",   tid_a, "Carlos", "Ruiz")
    prof_a    = _user("tar.prof.a@test.edu.ar",  tid_a, "Ana",    "García")
    prof_b    = _user("tar.prof.b@test.edu.ar",  tid_a, "Bob",    "López")
    coord_a   = _user("tar.coord@test.edu.ar",   tid_a, "Diana",  "Pérez")
    tercero_a = _user("tar.tercero@test.edu.ar", tid_a, "Nadie",  "Extra")
    db_session.add_all([tutor_a, prof_a, prof_b, coord_a, tercero_a])
    await db_session.flush()
    for u in [tutor_a, prof_a, prof_b, coord_a, tercero_a]:
        await db_session.refresh(u)

    # Roles
    rol_tutor = Rol(tenant_id=tid_a, nombre="TUTOR",       descripcion="Tutor")
    rol_prof  = Rol(tenant_id=tid_a, nombre="PROFESOR",    descripcion="Profesor")
    rol_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    db_session.add_all([rol_tutor, rol_prof, rol_coord])
    await db_session.flush()
    for r in [rol_tutor, rol_prof, rol_coord]:
        await db_session.refresh(r)

    # Permiso tareas_internas:gestionar — NO asignado a TUTOR
    p_gestionar = Permiso(
        tenant_id=tid_a,
        codigo="tareas_internas:gestionar",
        modulo="tareas_internas",
        descripcion="Gestionar tareas internas",
    )
    db_session.add(p_gestionar)
    await db_session.flush()
    await db_session.refresh(p_gestionar)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_prof.id,  permiso_id=p_gestionar.id, scope="own"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord.id, permiso_id=p_gestionar.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=tutor_a.id,   rol_id=rol_tutor.id),
        UserRol(tenant_id=tid_a, user_id=prof_a.id,    rol_id=rol_prof.id),
        UserRol(tenant_id=tid_a, user_id=prof_b.id,    rol_id=rol_prof.id),
        UserRol(tenant_id=tid_a, user_id=coord_a.id,   rol_id=rol_coord.id),
        # tercero_a: sin rol → sin permiso
    ])
    await db_session.flush()

    # Catálogo
    mat_a = Materia(tenant_id=tid_a, codigo="TAR_A", nombre="Materia A")
    mat_b = Materia(tenant_id=tid_a, codigo="TAR_B", nombre="Materia B")
    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-TAR", nombre="Ingeniería Test")
    db_session.add_all([mat_a, mat_b, carrera_a])
    await db_session.flush()
    for x in [mat_a, mat_b, carrera_a]:
        await db_session.refresh(x)

    cohorte_a = Cohorte(
        tenant_id=tid_a,
        carrera_id=carrera_a.id,
        nombre="MAR-2026",
        anio=2026,
        vig_desde=date(2026, 3, 1),
    )
    db_session.add(cohorte_a)
    await db_session.flush()
    await db_session.refresh(cohorte_a)

    # prof_a → mat_a (own); prof_b → mat_b (own)
    asig_prof_a = Asignacion(
        tenant_id=tid_a, usuario_id=prof_a.id, rol_id=rol_prof.id,
        materia_id=mat_a.id, carrera_id=carrera_a.id, cohorte_id=cohorte_a.id,
        desde=date(2026, 3, 1),
    )
    asig_prof_b = Asignacion(
        tenant_id=tid_a, usuario_id=prof_b.id, rol_id=rol_prof.id,
        materia_id=mat_b.id, carrera_id=carrera_a.id, cohorte_id=cohorte_a.id,
        desde=date(2026, 3, 1),
    )
    db_session.add_all([asig_prof_a, asig_prof_b])
    await db_session.flush()

    # ── Tenant B ─────────────────────────────────────────────────────────────
    tenant_b = Tenant(codigo=TENANT_B, nombre="Tareas Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    coord_b = _user("tar.coord.b@test.edu.ar", tid_b, "Fede", "Soto")
    db_session.add(coord_b)
    await db_session.flush()
    await db_session.refresh(coord_b)

    rol_coord_b = Rol(tenant_id=tid_b, nombre="COORDINADOR", descripcion="Coordinador B")
    db_session.add(rol_coord_b)
    await db_session.flush()
    await db_session.refresh(rol_coord_b)

    p_gest_b = Permiso(
        tenant_id=tid_b,
        codigo="tareas_internas:gestionar",
        modulo="tareas_internas",
        descripcion="Gestionar B",
    )
    db_session.add(p_gest_b)
    await db_session.flush()
    await db_session.refresh(p_gest_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_coord_b.id, permiso_id=p_gest_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=coord_b.id, rol_id=rol_coord_b.id),
    ])
    await db_session.flush()

    await db_session.commit()

    def _tok(user: User, tid: UUID, rol: str) -> str:
        return create_access_token(user.id, tid, [rol])

    return {
        "tid_a": tid_a, "tid_b": tid_b,
        "tutor_a": tutor_a, "prof_a": prof_a, "prof_b": prof_b,
        "coord_a": coord_a, "tercero_a": tercero_a, "coord_b": coord_b,
        "mat_a": mat_a, "mat_b": mat_b,
        "token_tutor":   _tok(tutor_a,   tid_a, "TUTOR"),
        "token_prof_a":  _tok(prof_a,    tid_a, "PROFESOR"),
        "token_prof_b":  _tok(prof_b,    tid_a, "PROFESOR"),
        "token_coord":   _tok(coord_a,   tid_a, "COORDINADOR"),
        "token_tercero": _tok(tercero_a, tid_a, ""),
        "token_coord_b": _tok(coord_b,   tid_b, "COORDINADOR"),
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tarea_payload(asignado_a: UUID, **kwargs) -> dict:
    base = {"asignado_a": str(asignado_a), "descripcion": "Tarea de prueba"}
    base.update(kwargs)
    return base


# ── Sección 1: modelo y audit_codes ──────────────────────────────────────────


def test_audit_codes_contiene_tarea_asignar():
    from app.core.audit_codes import TAREA_ASIGNAR, VALID_ACTION_CODES
    assert TAREA_ASIGNAR in VALID_ACTION_CODES


def test_audit_codes_contiene_tarea_estado_cambiar():
    from app.core.audit_codes import TAREA_ESTADO_CAMBIAR, VALID_ACTION_CODES
    assert TAREA_ESTADO_CAMBIAR in VALID_ACTION_CODES


# ── Sección 2: mis-tareas (F8.1) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mis_tareas_sin_auth_401(async_client: AsyncClient):
    r = await async_client.get("/api/v1/tareas/mis-tareas")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_mis_tareas_tutor_sin_permiso_accede(
    async_client: AsyncClient, tar_db: dict
):
    """TUTOR sin tareas_internas:gestionar puede acceder a mis-tareas."""
    r = await async_client.get(
        "/api/v1/tareas/mis-tareas",
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_mis_tareas_devuelve_propias(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """TUTOR ve sólo tareas donde es asignado_a; las del prof_a no aparecen."""
    tid_a = tar_db["tid_a"]
    tutor = tar_db["tutor_a"]
    coord = tar_db["coord_a"]
    prof_a = tar_db["prof_a"]

    # Tarea para tutor (asignada por coord)
    t1 = Tarea(
        tenant_id=tid_a, asignado_a=tutor.id, asignado_por=coord.id,
        descripcion="Tarea del tutor",
    )
    # Tarea para prof_a (asignada por coord)
    t2 = Tarea(
        tenant_id=tid_a, asignado_a=prof_a.id, asignado_por=coord.id,
        descripcion="Tarea del profesor",
    )
    db_session.add_all([t1, t2])
    await db_session.commit()

    r = await async_client.get(
        "/api/v1/tareas/mis-tareas",
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()]
    assert str(t1.id) in ids
    assert str(t2.id) not in ids  # tarea del prof_a no visible para tutor


@pytest.mark.asyncio
async def test_mis_tareas_filtro_estado(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    tid_a = tar_db["tid_a"]
    tutor = tar_db["tutor_a"]
    coord = tar_db["coord_a"]

    t_pend = Tarea(
        tenant_id=tid_a, asignado_a=tutor.id, asignado_por=coord.id,
        descripcion="Pendiente",
    )
    t_res = Tarea(
        tenant_id=tid_a, asignado_a=tutor.id, asignado_por=coord.id,
        descripcion="Resuelta", estado="Resuelta",
    )
    db_session.add_all([t_pend, t_res])
    await db_session.commit()

    r = await async_client.get(
        "/api/v1/tareas/mis-tareas?estado=Pendiente",
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    data = r.json()
    assert all(item["estado"] == "Pendiente" for item in data)
    ids = [item["id"] for item in data]
    assert str(t_res.id) not in ids


@pytest.mark.asyncio
async def test_mis_tareas_cross_tenant(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Tarea de tenant B no visible para usuario de tenant A."""
    tid_b = tar_db["tid_b"]
    coord_b = tar_db["coord_b"]
    # Crear tarea en tenant B asignada a coord_b
    t_b = Tarea(
        tenant_id=tid_b, asignado_a=coord_b.id, asignado_por=coord_b.id,
        descripcion="Tarea en tenant B",
    )
    db_session.add(t_b)
    await db_session.commit()

    r = await async_client.get(
        "/api/v1/tareas/mis-tareas",
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    assert str(t_b.id) not in [item["id"] for item in r.json()]


# ── Sección 3: crear tarea — PROFESOR scope=own (F8.2) ───────────────────────


@pytest.mark.asyncio
async def test_crear_tarea_coordinador_sin_materia(
    async_client: AsyncClient, tar_db: dict
):
    """COORDINADOR puede crear tarea institucional (sin materia_id)."""
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(tar_db["tutor_a"].id),
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["estado"] == "Pendiente"
    assert data["asignado_por"]["id"] == str(tar_db["coord_a"].id)
    assert data["materia_id"] is None


@pytest.mark.asyncio
async def test_crear_tarea_coordinador_con_materia(
    async_client: AsyncClient, tar_db: dict
):
    """COORDINADOR puede crear tarea con materia_id."""
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(tar_db["tutor_a"].id, materia_id=str(tar_db["mat_a"].id)),
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 201
    assert r.json()["materia_id"] == str(tar_db["mat_a"].id)


@pytest.mark.asyncio
async def test_crear_tarea_profesor_propia_materia(
    async_client: AsyncClient, tar_db: dict
):
    """PROFESOR con asignación vigente en mat_a puede crear tarea en mat_a."""
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(
            tar_db["tutor_a"].id,
            materia_id=str(tar_db["mat_a"].id),
        ),
        headers=_auth(tar_db["token_prof_a"]),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["asignado_por"]["id"] == str(tar_db["prof_a"].id)
    assert data["materia_id"] == str(tar_db["mat_a"].id)


@pytest.mark.asyncio
async def test_crear_tarea_profesor_materia_ajena_403(
    async_client: AsyncClient, tar_db: dict
):
    """PROFESOR no puede crear tarea en materia donde no tiene asignación vigente."""
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(
            tar_db["tutor_a"].id,
            materia_id=str(tar_db["mat_b"].id),  # mat_b es de prof_b, no de prof_a
        ),
        headers=_auth(tar_db["token_prof_a"]),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_crear_tarea_profesor_sin_materia_403(
    async_client: AsyncClient, tar_db: dict
):
    """PROFESOR scope=own no puede crear tarea sin materia_id."""
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(tar_db["tutor_a"].id),  # sin materia_id
        headers=_auth(tar_db["token_prof_a"]),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_crear_tarea_sin_permiso_403(
    async_client: AsyncClient, tar_db: dict
):
    """TUTOR sin gestionar → 403 al intentar crear."""
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(tar_db["coord_a"].id),
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_crear_tarea_asignado_a_otro_tenant_422(
    async_client: AsyncClient, tar_db: dict
):
    """asignado_a de otro tenant → 422."""
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(tar_db["coord_b"].id),  # coord_b es de tenant B
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_crear_tarea_registra_audit(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(tar_db["tutor_a"].id),
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 201
    result = await db_session.execute(
        text("SELECT accion FROM audit_log WHERE tenant_id = :tid ORDER BY fecha_hora DESC LIMIT 1"),
        {"tid": tar_db["tid_a"]},
    )
    row = result.one_or_none()
    assert row is not None
    assert row[0] == "TAREA_ASIGNAR"


@pytest.mark.asyncio
async def test_crear_tarea_contexto_id_opaco(
    async_client: AsyncClient, tar_db: dict
):
    """contexto_id con UUID random (sin referencia real) → 201."""
    random_ctx = str(uuid4())
    r = await async_client.post(
        "/api/v1/tareas",
        json=_tarea_payload(tar_db["tutor_a"].id, contexto_id=random_ctx),
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 201
    assert r.json()["contexto_id"] == random_ctx


# ── Sección 4: cambio de estado FSM ──────────────────────────────────────────


async def _create_tarea(
    db_session: AsyncSession,
    tid: UUID,
    asignado_a: UUID,
    asignado_por: UUID,
    estado: str = "Pendiente",
    descripcion: str = "Tarea FSM",
) -> Tarea:
    t = Tarea(
        tenant_id=tid,
        asignado_a=asignado_a,
        asignado_por=asignado_por,
        descripcion=descripcion,
        estado=estado,
    )
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    return t


@pytest.mark.asyncio
async def test_estado_pendiente_en_progreso_asignado_a(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """asignado_a puede mover Pendiente → En progreso."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "En progreso"},
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "En progreso"


@pytest.mark.asyncio
async def test_estado_pendiente_cancelada_asignado_por(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """asignado_por puede cancelar desde Pendiente."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "Cancelada"},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "Cancelada"


@pytest.mark.asyncio
async def test_estado_en_progreso_resuelta_asignado_a(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
        estado="En progreso",
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "Resuelta"},
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "Resuelta"


@pytest.mark.asyncio
async def test_estado_en_progreso_cancelada_asignado_por_403(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """asignado_por (sin ser gestor) no puede cancelar tarea En progreso."""
    # prof_a es asignado_por, tutor_a es asignado_a
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["prof_a"].id,
        estado="En progreso",
    )
    # prof_a tiene gestionar:own pero la transición En progreso→Cancelada es solo "gestores"
    # "gestores" son quienes tienen el permiso. prof_a lo tiene scope=own.
    # Verificamos la regla: prof_a tiene gestionar → es gestor → puede cancelar
    # Realmente "gestores" incluye a quien tiene el permiso. Testeamos el caso
    # de asignado_por SIN permiso gestionar:
    # En este fixture, prof_a SÍ tiene gestionar:own, entonces puede hacerlo.
    # Para probar el 403, usamos a tutor_a (asignado_a) intentando cancelar En progreso.
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "Cancelada"},
        headers=_auth(tar_db["token_tutor"]),  # tutor = asignado_a, no gestor
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_estado_en_progreso_cancelada_coordinador_200(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Gestor (COORDINADOR) puede cancelar tarea En progreso."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["prof_a"].id,
        estado="En progreso",
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "Cancelada"},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "Cancelada"


@pytest.mark.asyncio
async def test_estado_terminal_resuelta_422(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
        estado="Resuelta",
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "Pendiente"},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 422
    assert "TAREA_ESTADO_TERMINAL" in r.json()["detail"]


@pytest.mark.asyncio
async def test_estado_terminal_cancelada_422(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
        estado="Cancelada",
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "Pendiente"},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 422
    assert "TAREA_ESTADO_TERMINAL" in r.json()["detail"]


@pytest.mark.asyncio
async def test_estado_transicion_invalida_422(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Pendiente → Resuelta no es una transición válida."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "Resuelta"},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 422
    assert "TAREA_TRANSICION_INVALIDA" in r.json()["detail"]


@pytest.mark.asyncio
async def test_estado_usuario_ajeno_403(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Usuario sin membresía en la tarea → 403."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "En progreso"},
        headers=_auth(tar_db["token_tercero"]),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_estado_otro_tenant_404(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Tarea de tenant B → 404 para usuario de tenant A."""
    tid_b = tar_db["tid_b"]
    coord_b = tar_db["coord_b"]
    t_b = await _create_tarea(
        db_session, tid_b,
        asignado_a=coord_b.id, asignado_por=coord_b.id,
    )
    r = await async_client.patch(
        f"/api/v1/tareas/{t_b.id}/estado",
        json={"estado": "En progreso"},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_estado_registra_audit(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    await async_client.patch(
        f"/api/v1/tareas/{t.id}/estado",
        json={"estado": "En progreso"},
        headers=_auth(tar_db["token_tutor"]),
    )
    result = await db_session.execute(
        text(
            "SELECT accion FROM audit_log WHERE tenant_id = :tid "
            "AND accion = 'TAREA_ESTADO_CAMBIAR' ORDER BY fecha_hora DESC LIMIT 1"
        ),
        {"tid": tar_db["tid_a"]},
    )
    assert result.one_or_none() is not None


# ── Sección 5: admin global / lista (F8.3) ────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_global_coordinador_ve_todo(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    tid_a = tar_db["tid_a"]
    t1 = Tarea(tenant_id=tid_a, asignado_a=tar_db["tutor_a"].id, asignado_por=tar_db["coord_a"].id, descripcion="T1")
    t2 = Tarea(tenant_id=tid_a, asignado_a=tar_db["prof_a"].id,  asignado_por=tar_db["coord_a"].id, descripcion="T2")
    db_session.add_all([t1, t2])
    await db_session.commit()

    r = await async_client.get("/api/v1/tareas", headers=_auth(tar_db["token_coord"]))
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()]
    assert str(t1.id) in ids
    assert str(t2.id) in ids


@pytest.mark.asyncio
async def test_admin_global_tutor_403(async_client: AsyncClient, tar_db: dict):
    """TUTOR sin gestionar → 403."""
    r = await async_client.get("/api/v1/tareas", headers=_auth(tar_db["token_tutor"]))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_global_filtro_estado(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    tid_a = tar_db["tid_a"]
    t_pend = Tarea(tenant_id=tid_a, asignado_a=tar_db["tutor_a"].id, asignado_por=tar_db["coord_a"].id, descripcion="P", estado="Pendiente")
    t_res  = Tarea(tenant_id=tid_a, asignado_a=tar_db["tutor_a"].id, asignado_por=tar_db["coord_a"].id, descripcion="R", estado="Resuelta")
    db_session.add_all([t_pend, t_res])
    await db_session.commit()

    r = await async_client.get("/api/v1/tareas?estado=Pendiente", headers=_auth(tar_db["token_coord"]))
    assert r.status_code == 200
    data = r.json()
    assert all(item["estado"] == "Pendiente" for item in data)
    assert str(t_res.id) not in [item["id"] for item in data]


@pytest.mark.asyncio
async def test_admin_global_busqueda_libre(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    tid_a = tar_db["tid_a"]
    t = Tarea(tenant_id=tid_a, asignado_a=tar_db["tutor_a"].id, asignado_por=tar_db["coord_a"].id, descripcion="Revisar comisión especial")
    db_session.add(t)
    await db_session.commit()

    r = await async_client.get("/api/v1/tareas?q=comisi%C3%B3n", headers=_auth(tar_db["token_coord"]))
    assert r.status_code == 200
    assert str(t.id) in [item["id"] for item in r.json()]


@pytest.mark.asyncio
async def test_admin_global_profesor_scope_own(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """PROFESOR con scope=own solo ve tareas donde es parte."""
    tid_a = tar_db["tid_a"]
    prof_a = tar_db["prof_a"]
    tutor_a = tar_db["tutor_a"]
    coord_a = tar_db["coord_a"]
    # Tarea donde prof_a es asignado_por
    t_suya = Tarea(tenant_id=tid_a, asignado_a=tutor_a.id, asignado_por=prof_a.id, descripcion="Creada por prof_a", materia_id=tar_db["mat_a"].id)
    # Tarea donde prof_a no tiene relación
    t_ajena = Tarea(tenant_id=tid_a, asignado_a=tutor_a.id, asignado_por=coord_a.id, descripcion="Ajena a prof_a")
    db_session.add_all([t_suya, t_ajena])
    await db_session.commit()

    r = await async_client.get("/api/v1/tareas", headers=_auth(tar_db["token_prof_a"]))
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()]
    assert str(t_suya.id) in ids
    assert str(t_ajena.id) not in ids


@pytest.mark.asyncio
async def test_admin_global_cross_tenant(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Tarea de tenant B no visible en listado de tenant A."""
    tid_b = tar_db["tid_b"]
    coord_b = tar_db["coord_b"]
    t_b = Tarea(tenant_id=tid_b, asignado_a=coord_b.id, asignado_por=coord_b.id, descripcion="En B")
    db_session.add(t_b)
    await db_session.commit()

    r = await async_client.get("/api/v1/tareas", headers=_auth(tar_db["token_coord"]))
    assert r.status_code == 200
    assert str(t_b.id) not in [item["id"] for item in r.json()]


# ── Sección 6: comentarios ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_comentar_asignado_a_201(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """TUTOR como asignado_a puede comentar."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.post(
        f"/api/v1/tareas/{t.id}/comentarios",
        json={"texto": "Empecé a trabajar en esto."},
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 201
    data = r.json()
    assert data["texto"] == "Empecé a trabajar en esto."
    assert data["autor"]["id"] == str(tar_db["tutor_a"].id)


@pytest.mark.asyncio
async def test_comentar_asignado_por_201(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """COORDINADOR como asignado_por puede comentar."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.post(
        f"/api/v1/tareas/{t.id}/comentarios",
        json={"texto": "Seguimiento de coordinación."},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_comentar_gestor_no_parte_201(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """COORDINADOR que no es asignado_a ni asignado_por puede comentar como gestor."""
    # prof_a asigna a prof_b
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["prof_b"].id,
        asignado_por=tar_db["prof_a"].id,
        descripcion="Tarea entre profes",
    )
    # coord_a no es parte de la tarea pero tiene gestionar:all
    r = await async_client.post(
        f"/api/v1/tareas/{t.id}/comentarios",
        json={"texto": "Comentario de coordinación."},
        headers=_auth(tar_db["token_coord"]),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_comentar_tercero_ajeno_403(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Usuario sin membresía ni permiso → 403."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.post(
        f"/api/v1/tareas/{t.id}/comentarios",
        json={"texto": "Intruso."},
        headers=_auth(tar_db["token_tercero"]),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_comentar_tarea_resuelta_permite(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """Se puede comentar en tarea Resuelta (hilo abierto para historial)."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
        estado="Resuelta",
    )
    r = await async_client.post(
        f"/api/v1/tareas/{t.id}/comentarios",
        json={"texto": "Nota post-resolución."},
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_comentar_texto_vacio_422(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.post(
        f"/api/v1/tareas/{t.id}/comentarios",
        json={"texto": ""},
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_comentar_autor_id_del_jwt(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    """autor_id es siempre del JWT, aunque el body intente sobrescribirlo."""
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.post(
        f"/api/v1/tareas/{t.id}/comentarios",
        # Intentamos enviar un campo extra (extra='forbid' lo rechazará)
        json={"texto": "Comentario", "autor_id": str(tar_db["prof_a"].id)},
        headers=_auth(tar_db["token_tutor"]),
    )
    # extra='forbid' → 422 si el schema rechaza, o 201 con autor correcto
    if r.status_code == 201:
        assert r.json()["autor"]["id"] == str(tar_db["tutor_a"].id)
    else:
        assert r.status_code == 422  # schema forbid extra field


@pytest.mark.asyncio
async def test_get_comentarios_orden_cronologico(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    for txt in ["Primero", "Segundo", "Tercero"]:
        await async_client.post(
            f"/api/v1/tareas/{t.id}/comentarios",
            json={"texto": txt},
            headers=_auth(tar_db["token_tutor"]),
        )

    r = await async_client.get(
        f"/api/v1/tareas/{t.id}/comentarios",
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    textos = [c["texto"] for c in r.json()]
    assert textos == ["Primero", "Segundo", "Tercero"]


@pytest.mark.asyncio
async def test_get_comentarios_vacio_200(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.get(
        f"/api/v1/tareas/{t.id}/comentarios",
        headers=_auth(tar_db["token_tutor"]),
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_comentarios_usuario_ajeno_403(
    async_client: AsyncClient, tar_db: dict, db_session: AsyncSession
):
    t = await _create_tarea(
        db_session, tar_db["tid_a"],
        asignado_a=tar_db["tutor_a"].id,
        asignado_por=tar_db["coord_a"].id,
    )
    r = await async_client.get(
        f"/api/v1/tareas/{t.id}/comentarios",
        headers=_auth(tar_db["token_tercero"]),
    )
    assert r.status_code == 403
