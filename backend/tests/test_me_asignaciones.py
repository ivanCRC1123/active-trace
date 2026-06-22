"""GET /api/v1/me/asignaciones — integration tests (C-22 prep).

Covers:
- Devuelve las asignaciones vigentes del usuario autenticado
- NO devuelve asignaciones de otro usuario del mismo tenant
- Devuelve lista vacía si el usuario no tiene asignaciones
- 401 sin autenticación
"""

from datetime import date
from uuid import uuid4

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
from app.models.rol import Rol
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_CODE = "me-asig-test"
USER_PASS = "Admin123!"
PROF_EMAIL = "me.prof@test.edu.ar"
OTHER_EMAIL = "me.other@test.edu.ar"
EMPTY_EMAIL = "me.empty@test.edu.ar"


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


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": TENANT_CODE, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def me_db(db_session: AsyncSession) -> dict:
    """Seed: un tenant con tres usuarios (prof, other, empty).

    - prof: tiene una asignación vigente con materia + cohorte
    - other: tiene una asignación vigente diferente (misma materia)
    - empty: sin asignaciones
    """
    for tbl in (
        "asignacion",
        "audit_log",
        "cohorte",
        "materia",
        "carrera",
        "user_rol",
        "rol_permiso",
        "permiso",
        "rol",
        "refresh_token",
        "recovery_token",
        '"user"',
        "tenant",
    ):
        await db_session.execute(text(f"DELETE FROM {tbl}"))
    await db_session.commit()

    tenant = Tenant(codigo=TENANT_CODE, nombre="Me Asig Test")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    tid = tenant.id

    prof = _user(PROF_EMAIL, tid)
    other = _user(OTHER_EMAIL, tid)
    empty = _user(EMPTY_EMAIL, tid)
    db_session.add_all([prof, other, empty])
    await db_session.flush()
    for u in (prof, other, empty):
        await db_session.refresh(u)

    rol_prof = Rol(tenant_id=tid, nombre="PROFESOR", descripcion="Profesor")
    db_session.add(rol_prof)
    await db_session.flush()
    await db_session.refresh(rol_prof)

    db_session.add_all([
        UserRol(tenant_id=tid, user_id=prof.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid, user_id=other.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid, user_id=empty.id, rol_id=rol_prof.id),
    ])
    await db_session.flush()

    carrera = Carrera(tenant_id=tid, codigo="CAR", nombre="Carrera Test", estado="Activa")
    db_session.add(carrera)
    await db_session.flush()
    await db_session.refresh(carrera)

    cohorte = Cohorte(
        tenant_id=tid,
        carrera_id=carrera.id,
        nombre="MAR-2026",
        anio=2026,
        vig_desde=date(2026, 3, 1),
        estado="Activa",
    )
    db_session.add(cohorte)
    await db_session.flush()
    await db_session.refresh(cohorte)

    materia = Materia(tenant_id=tid, codigo="MAT-ME", nombre="Materia Me Test", estado="Activa")
    db_session.add(materia)
    await db_session.flush()
    await db_session.refresh(materia)

    asig_prof = Asignacion(
        tenant_id=tid,
        usuario_id=prof.id,
        rol_id=rol_prof.id,
        materia_id=materia.id,
        cohorte_id=cohorte.id,
        carrera_id=carrera.id,
        desde=date(2026, 3, 1),
    )
    asig_other = Asignacion(
        tenant_id=tid,
        usuario_id=other.id,
        rol_id=rol_prof.id,
        materia_id=materia.id,
        cohorte_id=cohorte.id,
        carrera_id=carrera.id,
        desde=date(2026, 3, 1),
    )
    db_session.add_all([asig_prof, asig_other])
    await db_session.flush()
    for a in (asig_prof, asig_other):
        await db_session.refresh(a)
    await db_session.commit()

    return {
        "tenant_id": tid,
        "prof_id": prof.id,
        "other_id": other.id,
        "empty_id": empty.id,
        "asig_prof_id": asig_prof.id,
        "asig_other_id": asig_other.id,
        "materia_id": materia.id,
        "materia_nombre": "Materia Me Test",
        "cohorte_id": cohorte.id,
        "cohorte_nombre": "MAR-2026",
        "carrera_id": carrera.id,
        "carrera_nombre": "Carrera Test",
        "rol_nombre": "PROFESOR",
    }


@pytest.mark.asyncio
class TestGetMisAsignaciones:
    async def test_devuelve_asignaciones_propias(self, async_client: AsyncClient, me_db: dict):
        token = await _login(async_client, PROF_EMAIL)
        resp = await async_client.get("/api/v1/me/asignaciones", headers=_auth(token))

        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1

        item = body[0]
        assert item["id"] == str(me_db["asig_prof_id"])
        assert item["materia_id"] == str(me_db["materia_id"])
        assert item["materia_nombre"] == me_db["materia_nombre"]
        assert item["cohorte_id"] == str(me_db["cohorte_id"])
        assert item["cohorte_nombre"] == me_db["cohorte_nombre"]
        assert item["carrera_id"] == str(me_db["carrera_id"])
        assert item["carrera_nombre"] == me_db["carrera_nombre"]
        assert item["rol_nombre"] == me_db["rol_nombre"]
        assert item["desde"] == "2026-03-01"
        assert item["hasta"] is None
        assert item["comisiones"] == []

    async def test_no_devuelve_asignaciones_de_otro_usuario(
        self, async_client: AsyncClient, me_db: dict
    ):
        token = await _login(async_client, PROF_EMAIL)
        resp = await async_client.get("/api/v1/me/asignaciones", headers=_auth(token))

        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert str(me_db["asig_other_id"]) not in ids

    async def test_lista_vacia_si_sin_asignaciones(
        self, async_client: AsyncClient, me_db: dict
    ):
        token = await _login(async_client, EMPTY_EMAIL)
        resp = await async_client.get("/api/v1/me/asignaciones", headers=_auth(token))

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_401_sin_autenticacion(self, async_client: AsyncClient, me_db: dict):
        resp = await async_client.get("/api/v1/me/asignaciones")
        assert resp.status_code == 401
