"""C-13 encuentros-y-guardias (Sección 2) — tests de integración (F6.6).

Cubre por propiedad:
- TUTOR/PROFESOR registran guardia propia (asignacion_id propio) → 201, estado=Pendiente
- TUTOR/PROFESOR con asignacion_id ajena → 403
- COORDINADOR registra en nombre de cualquier asignacion del tenant → 201
- Scoping: TUTOR/PROFESOR solo ven sus propias guardias; COORDINADOR ve todo el tenant
- Edición: propietario 200, ajeno 403, COORDINADOR cualquiera 200
- Export CSV: COORDINADOR 200 (text/csv), TUTOR 403
- Tenant isolation: guardia de tenant A invisible para COORDINADOR de tenant B
- Transiciones de estado: Pendiente → Realizada, Pendiente → Cancelada
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
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_A = "grd-test-a"
TENANT_B = "grd-test-b"
USER_PASS = "Test123!"

MARTES = date(2026, 9, 8)


async def _delete_grd_tenant_data(session: AsyncSession, *codes: str) -> None:
    """Remove grd test data scoped to specific tenant codes only."""
    for code in codes:
        tid_sub = "(SELECT id FROM tenant WHERE codigo = :c)"
        await session.execute(
            text(f"DELETE FROM guardia WHERE tenant_id IN {tid_sub}"),
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
async def grd_db(db_session: AsyncSession) -> dict:
    """
    Tenant A: tutor_a (TUTOR/own), prof_a (PROFESOR/own), prof_b (PROFESOR/own),
              coord_a (COORDINADOR/all).
    Cada usuario tiene su asignacion en materia propia.
    Tenant B: coord_b (COORDINADOR/all) para tenant isolation.
    """
    await _delete_grd_tenant_data(db_session, TENANT_A, TENANT_B)

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
    tenant_a = Tenant(codigo=TENANT_A, nombre="Guardias Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    tutor_a = _user("grd.tutor.a@test.edu.ar", tid_a, "Carlos", "Ruiz")
    prof_a = _user("grd.prof.a@test.edu.ar", tid_a, "Ana", "García")
    prof_b = _user("grd.prof.b@test.edu.ar", tid_a, "Bob", "López")
    coord_a = _user("grd.coord.a@test.edu.ar", tid_a, "Diana", "Pérez")
    db_session.add_all([tutor_a, prof_a, prof_b, coord_a])
    await db_session.flush()
    for u in [tutor_a, prof_a, prof_b, coord_a]:
        await db_session.refresh(u)

    # Roles
    rol_tutor = Rol(tenant_id=tid_a, nombre="TUTOR", descripcion="Tutor")
    rol_prof = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    rol_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    db_session.add_all([rol_tutor, rol_prof, rol_coord])
    await db_session.flush()
    for r in [rol_tutor, rol_prof, rol_coord]:
        await db_session.refresh(r)

    # Permiso guardias:registrar
    p_grd = Permiso(
        tenant_id=tid_a,
        codigo="guardias:registrar",
        modulo="guardias",
        descripcion="Registrar guardias",
    )
    db_session.add(p_grd)
    await db_session.flush()
    await db_session.refresh(p_grd)

    # TUTOR y PROFESOR: scope="own"; COORDINADOR: scope="all"
    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_tutor.id, permiso_id=p_grd.id, scope="own"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_prof.id, permiso_id=p_grd.id, scope="own"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord.id, permiso_id=p_grd.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=tutor_a.id, rol_id=rol_tutor.id),
        UserRol(tenant_id=tid_a, user_id=prof_a.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid_a, user_id=prof_b.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid_a, user_id=coord_a.id, rol_id=rol_coord.id),
    ])
    await db_session.flush()

    # Catálogo
    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-GRD", nombre="Ingeniería")
    mat_a = Materia(tenant_id=tid_a, codigo="GRD_I", nombre="Cálculo I")
    mat_b = Materia(tenant_id=tid_a, codigo="GRD_II", nombre="Cálculo II")
    mat_c = Materia(tenant_id=tid_a, codigo="GRD_III", nombre="Álgebra")
    db_session.add_all([carrera_a, mat_a, mat_b, mat_c])
    await db_session.flush()
    for m in [carrera_a, mat_a, mat_b, mat_c]:
        await db_session.refresh(m)

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

    # Asignaciones: cada docente en materia diferente
    asig_tutor = Asignacion(
        tenant_id=tid_a, usuario_id=tutor_a.id, rol_id=rol_tutor.id,
        materia_id=mat_a.id, carrera_id=carrera_a.id, cohorte_id=cohorte_a.id,
        desde=date(2026, 3, 1),
    )
    asig_prof_a = Asignacion(
        tenant_id=tid_a, usuario_id=prof_a.id, rol_id=rol_prof.id,
        materia_id=mat_b.id, carrera_id=carrera_a.id, cohorte_id=cohorte_a.id,
        desde=date(2026, 3, 1),
    )
    asig_prof_b = Asignacion(
        tenant_id=tid_a, usuario_id=prof_b.id, rol_id=rol_prof.id,
        materia_id=mat_c.id, carrera_id=carrera_a.id, cohorte_id=cohorte_a.id,
        desde=date(2026, 3, 1),
    )
    db_session.add_all([asig_tutor, asig_prof_a, asig_prof_b])
    await db_session.flush()
    for a in [asig_tutor, asig_prof_a, asig_prof_b]:
        await db_session.refresh(a)

    # ── Tenant B ─────────────────────────────────────────────────────────────
    tenant_b = Tenant(codigo=TENANT_B, nombre="Guardias Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    coord_b = _user("grd.coord.b@test.edu.ar", tid_b, "Fede", "Soto")
    db_session.add(coord_b)
    await db_session.flush()
    await db_session.refresh(coord_b)

    rol_coord_b = Rol(tenant_id=tid_b, nombre="COORDINADOR", descripcion="Coordinador B")
    db_session.add(rol_coord_b)
    await db_session.flush()
    await db_session.refresh(rol_coord_b)

    p_grd_b = Permiso(
        tenant_id=tid_b, codigo="guardias:registrar", modulo="guardias",
        descripcion="Registrar guardias B",
    )
    db_session.add(p_grd_b)
    await db_session.flush()
    await db_session.refresh(p_grd_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_coord_b.id, permiso_id=p_grd_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=coord_b.id, rol_id=rol_coord_b.id),
    ])

    mat_b2 = Materia(tenant_id=tid_b, codigo="GRD_B", nombre="Materia B")
    carrera_b = Carrera(tenant_id=tid_b, codigo="ING-B-GRD", nombre="Ing B")
    db_session.add_all([mat_b2, carrera_b])
    await db_session.flush()
    await db_session.refresh(mat_b2)
    await db_session.refresh(carrera_b)

    cohorte_b = Cohorte(
        tenant_id=tid_b, carrera_id=carrera_b.id, nombre="MAR-2026", anio=2026,
        vig_desde=date(2026, 3, 1),
    )
    db_session.add(cohorte_b)
    await db_session.flush()
    await db_session.refresh(cohorte_b)

    asig_coord_b = Asignacion(
        tenant_id=tid_b, usuario_id=coord_b.id, rol_id=rol_coord_b.id,
        materia_id=mat_b2.id, carrera_id=carrera_b.id, cohorte_id=cohorte_b.id,
        desde=date(2026, 3, 1),
    )
    db_session.add(asig_coord_b)
    await db_session.flush()
    await db_session.refresh(asig_coord_b)

    await db_session.commit()

    def _token(user: User, tid: UUID, rol: str) -> str:
        return create_access_token(user.id, tid, [rol])

    return {
        "tid_a": tid_a, "tid_b": tid_b,
        "tutor_a": tutor_a, "prof_a": prof_a, "prof_b": prof_b, "coord_a": coord_a,
        "coord_b": coord_b,
        "carrera_a": carrera_a, "cohorte_a": cohorte_a,
        "mat_a": mat_a, "mat_b": mat_b, "mat_c": mat_c,
        "asig_tutor": asig_tutor, "asig_prof_a": asig_prof_a, "asig_prof_b": asig_prof_b,
        "token_tutor_a": _token(tutor_a, tid_a, "TUTOR"),
        "token_prof_a": _token(prof_a, tid_a, "PROFESOR"),
        "token_prof_b": _token(prof_b, tid_a, "PROFESOR"),
        "token_coord_a": _token(coord_a, tid_a, "COORDINADOR"),
        "token_coord_b": _token(coord_b, tid_b, "COORDINADOR"),
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _payload(asig_id: UUID, mat_id: UUID, **kwargs) -> dict:
    base = {
        "asignacion_id": str(asig_id),
        "materia_id": str(mat_id),
        "dia": "Martes",
        "fecha": str(MARTES),
        "horario": "14:00-14:45",
    }
    base.update(kwargs)
    return base


# ── TestGuardiaRegistrar ─────────────────────────────────────────────────────


class TestGuardiaRegistrar:
    async def test_tutor_registra_propia_201(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["estado"] == "Pendiente"
        assert body["asignacion_id"] == str(grd_db["asig_tutor"].id)
        assert body["dia"] == "Martes"

    async def test_tutor_registra_ajena_403(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        # tutor_a intenta usar asig_prof_a (de prof_a) → 403
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_prof_a"].id, grd_db["mat_b"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r.status_code == 403

    async def test_profesor_registra_propia_201(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_prof_a"].id, grd_db["mat_b"].id),
            headers=_auth(grd_db["token_prof_a"]),
        )
        assert r.status_code == 201
        assert r.json()["estado"] == "Pendiente"

    async def test_coordinador_registra_cualquier_asignacion_201(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        # coord_a (scope="all") usa asig_tutor (de otro usuario) → 201
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r.status_code == 201

    async def test_sin_auth_401(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
        )
        assert r.status_code == 401

    async def test_asignacion_inexistente_422(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(uuid4(), grd_db["mat_a"].id),
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r.status_code == 422

    async def test_estado_inicial_siempre_pendiente(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        # GuardiaCreate no acepta estado (extra='forbid') → Pydantic rechaza si se envía
        r = await async_client.post(
            "/api/v1/guardias/",
            json={**_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id), "estado": "Realizada"},
            headers=_auth(grd_db["token_tutor_a"]),
        )
        # extra='forbid' rechaza el campo desconocido → 422
        assert r.status_code == 422


# ── TestGuardiaListar ─────────────────────────────────────────────────────────


class TestGuardiaListar:
    async def test_tutor_solo_ve_propias(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        # Crear guardia para tutor_a y para prof_a
        await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_prof_a"].id, grd_db["mat_b"].id),
            headers=_auth(grd_db["token_prof_a"]),
        )
        r = await async_client.get(
            "/api/v1/guardias/",
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r.status_code == 200
        guardias = r.json()
        assert all(
            g["asignacion_id"] == str(grd_db["asig_tutor"].id)
            for g in guardias
        )

    async def test_coordinador_ve_todas(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_prof_a"].id, grd_db["mat_b"].id),
            headers=_auth(grd_db["token_prof_a"]),
        )
        r = await async_client.get(
            "/api/v1/guardias/",
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r.status_code == 200
        ids = {g["asignacion_id"] for g in r.json()}
        assert str(grd_db["asig_tutor"].id) in ids
        assert str(grd_db["asig_prof_a"].id) in ids

    async def test_filtro_por_estado(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        # Crear guardia y luego cambiarla a Realizada
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        gid = r.json()["id"]
        await async_client.patch(
            f"/api/v1/guardias/{gid}",
            json={"estado": "Realizada"},
            headers=_auth(grd_db["token_tutor_a"]),
        )

        # También crear una Pendiente
        await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )

        r = await async_client.get(
            "/api/v1/guardias/?estado=Realizada",
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r.status_code == 200
        guardias = r.json()
        assert all(g["estado"] == "Realizada" for g in guardias)
        assert len(guardias) >= 1

    async def test_filtro_por_fecha(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r.status_code == 201

        # Filtro que incluye la fecha → debe aparecer
        r_inc = await async_client.get(
            f"/api/v1/guardias/?fecha_desde=2026-09-01&fecha_hasta=2026-09-30",
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r_inc.status_code == 200
        assert len(r_inc.json()) >= 1

        # Filtro que excluye la fecha → debe estar vacío
        r_exc = await async_client.get(
            "/api/v1/guardias/?fecha_desde=2026-10-01",
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r_exc.status_code == 200
        assert len(r_exc.json()) == 0


# ── TestGuardiaEditar ─────────────────────────────────────────────────────────


class TestGuardiaEditar:
    async def test_tutor_edita_propia_200(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        gid = r.json()["id"]

        r2 = await async_client.patch(
            f"/api/v1/guardias/{gid}",
            json={"estado": "Realizada", "comentarios": "Sin novedades"},
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r2.status_code == 200
        body = r2.json()
        assert body["estado"] == "Realizada"
        assert body["comentarios"] == "Sin novedades"

    async def test_tutor_edita_ajena_403(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_prof_a"].id, grd_db["mat_b"].id),
            headers=_auth(grd_db["token_prof_a"]),
        )
        gid = r.json()["id"]

        r2 = await async_client.patch(
            f"/api/v1/guardias/{gid}",
            json={"estado": "Realizada"},
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r2.status_code == 403

    async def test_coordinador_edita_cualquier_guardia_200(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        gid = r.json()["id"]

        r2 = await async_client.patch(
            f"/api/v1/guardias/{gid}",
            json={"estado": "Cancelada"},
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r2.status_code == 200
        assert r2.json()["estado"] == "Cancelada"

    async def test_campo_no_editable_422(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        gid = r.json()["id"]

        # materia_id no está en GuardiaUpdate (extra='forbid') → 422
        r2 = await async_client.patch(
            f"/api/v1/guardias/{gid}",
            json={"materia_id": str(grd_db["mat_b"].id)},
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r2.status_code == 422


# ── TestGuardiaExport ─────────────────────────────────────────────────────────


class TestGuardiaExport:
    async def test_coordinador_exporta_csv_200(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        r = await async_client.get(
            "/api/v1/guardias/export",
            headers=_auth(grd_db["token_coord_a"]),
        )
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        # CSV tiene al menos la línea de cabecera
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("asignacion_id")
        assert len(lines) >= 2  # cabecera + 1 fila

    async def test_tutor_no_puede_exportar_403(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.get(
            "/api/v1/guardias/export",
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r.status_code == 403


# ── TestGuardiaTenantIsolation ────────────────────────────────────────────────


class TestGuardiaTenantIsolation:
    async def test_guardia_tenant_a_invisible_para_coord_b(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        # Crear guardia en tenant A
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r.status_code == 201
        gid = r.json()["id"]

        # coord_b (tenant B) lista → no debe ver la guardia de tenant A
        r2 = await async_client.get(
            "/api/v1/guardias/",
            headers=_auth(grd_db["token_coord_b"]),
        )
        assert r2.status_code == 200
        ids = [g["id"] for g in r2.json()]
        assert gid not in ids


# ── TestGuardiaEstado ─────────────────────────────────────────────────────────


class TestGuardiaEstado:
    async def test_estado_inicial_pendiente(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r.status_code == 201
        assert r.json()["estado"] == "Pendiente"

    async def test_transicion_pendiente_a_realizada(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        gid = r.json()["id"]
        r2 = await async_client.patch(
            f"/api/v1/guardias/{gid}",
            json={"estado": "Realizada"},
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r2.status_code == 200
        assert r2.json()["estado"] == "Realizada"

    async def test_transicion_pendiente_a_cancelada(
        self, async_client: AsyncClient, grd_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/guardias/",
            json=_payload(grd_db["asig_tutor"].id, grd_db["mat_a"].id),
            headers=_auth(grd_db["token_tutor_a"]),
        )
        gid = r.json()["id"]
        r2 = await async_client.patch(
            f"/api/v1/guardias/{gid}",
            json={"estado": "Cancelada"},
            headers=_auth(grd_db["token_tutor_a"]),
        )
        assert r2.status_code == 200
        assert r2.json()["estado"] == "Cancelada"
