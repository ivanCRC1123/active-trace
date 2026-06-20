"""C-09 Moodle WS client tests.

Covers:
- FakeMoodleWSClient: returns participants / raises on demand / empty default
- Protocol compliance (duck-typing isinstance check)
- Sincronizar-moodle endpoint: 201 happy path, 502 on WS error,
  503 when MOODLE_BASE_URL not configured, 400 when materia has no moodle_course_id
"""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt, hmac_email
from app.core.security import hash_password
from app.integrations.moodle_ws import (
    FakeMoodleWSClient,
    MoodleParticipant,
    MoodleWSClientProtocol,
    MoodleWSError,
)
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_CODE = "moodle-test"
USER_PASS = "Admin123!"
COORD_EMAIL = "moodle.coord@test.edu.ar"

FAKE_PARTICIPANTS: list[MoodleParticipant] = [
    MoodleParticipant(nombre="Pedro", apellidos="Pérez", email="pedro@moodle.edu", comision="A", regional=None),
    MoodleParticipant(nombre="Lucía", apellidos="Gómez", email="lucia@moodle.edu", comision=None, regional=None),
]


# ── Unit tests — FakeMoodleWSClient ───────────────────────────────────────────


@pytest.mark.asyncio
class TestFakeMoodleWSClient:
    async def test_returns_configured_participants(self) -> None:
        client = FakeMoodleWSClient(participants=FAKE_PARTICIPANTS)
        result = await client.get_participants("42")
        assert result == FAKE_PARTICIPANTS

    async def test_empty_by_default(self) -> None:
        client = FakeMoodleWSClient()
        result = await client.get_participants("99")
        assert result == []

    async def test_raises_moodle_ws_error_when_configured(self) -> None:
        client = FakeMoodleWSClient(raises=True)
        with pytest.raises(MoodleWSError):
            await client.get_participants("1")

    def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeMoodleWSClient(), MoodleWSClientProtocol)


# ── Fixture for endpoint integration tests ─────────────────────────────────────


def _make_user(email: str, tid) -> User:
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


@pytest_asyncio.fixture
async def moodle_db(db_session: AsyncSession) -> dict:
    """Minimal seed: one tenant with a COORDINADOR user (padron:cargar scope=all),
    materia_con_course_id (moodle_course_id='42') and materia_sin_course_id (NULL).
    """
    await db_session.execute(text("DELETE FROM entrada_padron"))
    await db_session.execute(text("DELETE FROM version_padron"))
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

    tenant = Tenant(codigo=TENANT_CODE, nombre="Moodle Test")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    tid = tenant.id

    coord = _make_user(COORD_EMAIL, tid)
    db_session.add(coord)
    await db_session.flush()
    await db_session.refresh(coord)

    rol = Rol(tenant_id=tid, nombre="COORDINADOR", descripcion="Coord")
    db_session.add(rol)
    await db_session.flush()
    await db_session.refresh(rol)

    p_cargar = Permiso(tenant_id=tid, codigo="padron:cargar", modulo="padron", descripcion="Cargar")
    p_ver = Permiso(tenant_id=tid, codigo="padron:ver", modulo="padron", descripcion="Ver")
    db_session.add_all([p_cargar, p_ver])
    await db_session.flush()
    await db_session.refresh(p_cargar)
    await db_session.refresh(p_ver)

    db_session.add_all([
        RolPermiso(tenant_id=tid, rol_id=rol.id, permiso_id=p_cargar.id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol.id, permiso_id=p_ver.id, scope="all"),
        UserRol(tenant_id=tid, user_id=coord.id, rol_id=rol.id),
    ])
    await db_session.flush()

    carrera = Carrera(tenant_id=tid, codigo="ING", nombre="Ingeniería")
    db_session.add(carrera)
    await db_session.flush()
    await db_session.refresh(carrera)

    cohorte = Cohorte(
        tenant_id=tid, carrera_id=carrera.id, nombre="2026-1",
        anio=2026, vig_desde=date(2026, 1, 1),
    )
    db_session.add(cohorte)
    await db_session.flush()
    await db_session.refresh(cohorte)

    materia_con = Materia(
        tenant_id=tid, codigo="MAT101", nombre="Matemática I",
        moodle_course_id="42",
    )
    materia_sin = Materia(
        tenant_id=tid, codigo="MAT102", nombre="Matemática II",
    )
    db_session.add_all([materia_con, materia_sin])
    await db_session.flush()
    await db_session.refresh(materia_con)
    await db_session.refresh(materia_sin)

    await db_session.commit()

    return {
        "tid": tid,
        "materia_con_id": materia_con.id,
        "materia_sin_id": materia_sin.id,
        "cohorte_id": cohorte.id,
    }


async def _login(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": TENANT_CODE, "email": COORD_EMAIL, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _sync_url(mid, cid) -> str:
    return f"/api/v1/padron/{mid}/cohortes/{cid}/sincronizar-moodle"


# ── Integration tests — sincronizar-moodle endpoint ───────────────────────────


@pytest.mark.asyncio
class TestSincronizarMoodleEndpoint:
    async def test_sync_ok_201(
        self, async_client: AsyncClient, moodle_db: dict, app, monkeypatch
    ) -> None:
        from app.core import config as app_config  # noqa: PLC0415
        from app.core.dependencies import get_moodle_client  # noqa: PLC0415

        monkeypatch.setattr(app_config.settings, "MOODLE_BASE_URL", "http://moodle.test.edu")

        fake = FakeMoodleWSClient(participants=FAKE_PARTICIPANTS)
        app.dependency_overrides[get_moodle_client] = lambda: fake
        try:
            token = await _login(async_client)
            d = moodle_db
            resp = await async_client.post(
                _sync_url(d["materia_con_id"], d["cohorte_id"]),
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            app.dependency_overrides.pop(get_moodle_client, None)

        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["total_importadas"] == 2
        assert data["version"]["activa"] is True

    async def test_moodle_ws_error_502(
        self, async_client: AsyncClient, moodle_db: dict, app, monkeypatch
    ) -> None:
        from app.core import config as app_config  # noqa: PLC0415
        from app.core.dependencies import get_moodle_client  # noqa: PLC0415

        monkeypatch.setattr(app_config.settings, "MOODLE_BASE_URL", "http://moodle.test.edu")

        fake = FakeMoodleWSClient(raises=True)
        app.dependency_overrides[get_moodle_client] = lambda: fake
        try:
            token = await _login(async_client)
            d = moodle_db
            resp = await async_client.post(
                _sync_url(d["materia_con_id"], d["cohorte_id"]),
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            app.dependency_overrides.pop(get_moodle_client, None)

        assert resp.status_code == 502

    async def test_moodle_no_configurado_503(
        self, async_client: AsyncClient, moodle_db: dict
    ) -> None:
        # MOODLE_BASE_URL defaults to "" → service raises moodle_no_configurado
        token = await _login(async_client)
        d = moodle_db
        resp = await async_client.post(
            _sync_url(d["materia_con_id"], d["cohorte_id"]),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 503

    async def test_materia_sin_course_id_400(
        self, async_client: AsyncClient, moodle_db: dict, app, monkeypatch
    ) -> None:
        from app.core import config as app_config  # noqa: PLC0415
        from app.core.dependencies import get_moodle_client  # noqa: PLC0415

        monkeypatch.setattr(app_config.settings, "MOODLE_BASE_URL", "http://moodle.test.edu")

        fake = FakeMoodleWSClient(participants=FAKE_PARTICIPANTS)
        app.dependency_overrides[get_moodle_client] = lambda: fake
        try:
            token = await _login(async_client)
            d = moodle_db
            resp = await async_client.post(
                _sync_url(d["materia_sin_id"], d["cohorte_id"]),
                headers={"Authorization": f"Bearer {token}"},
            )
        finally:
            app.dependency_overrides.pop(get_moodle_client, None)

        assert resp.status_code == 400
