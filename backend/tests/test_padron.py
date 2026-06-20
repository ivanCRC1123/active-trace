"""C-09 padrón ingesta — integration tests.

Covers:
- Import xlsx/csv file (preview + confirm)
- Versioning: new import deactivates previous version
- Auto-link: email_hash match → usuario_id set
- Tenant isolation (cross-tenant lookups → 404 / no link)
- Vaciar: COORDINADOR (any) / PROFESOR (own only)
- RBAC: missing permission → 403
- PII: email_cifrado in DB is ciphertext; response has plaintext
"""

from __future__ import annotations

import csv
import io
from datetime import date
from uuid import UUID

import openpyxl
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
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

TENANT_CODE_A = "padron-test-a"
TENANT_CODE_B = "padron-test-b"
USER_PASS = "Admin123!"

COORD_EMAIL = "padron.coord@test.edu.ar"
PROF_EMAIL = "padron.prof@test.edu.ar"
NOPERM_EMAIL = "padron.noperm@test.edu.ar"
ALUMNO_EXISTENTE_EMAIL = "alumno.existente@test.edu.ar"
COORD_B_EMAIL = "padron.coord.b@test.edu.ar"


# ── File helpers ───────────────────────────────────────────────────────────────


def _make_xlsx(rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = ["nombre", "apellidos", "email", "comision", "regional"]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    headers = ["nombre", "apellidos", "email", "comision", "regional"]
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow({h: row.get(h, "") for h in headers})
    return buf.getvalue().encode("utf-8")


SAMPLE_ROWS = [
    {"nombre": "Ana", "apellidos": "García", "email": "ana@test.edu", "comision": "A"},
    {"nombre": "Bob", "apellidos": "López", "email": "bob@test.edu", "comision": "B"},
    {"nombre": "Clara", "apellidos": "Ruiz", "email": "clara@test.edu"},
]


def _xlsx_files(rows: list[dict] | None = None) -> dict:
    content = _make_xlsx(rows or SAMPLE_ROWS)
    return {"file": ("alumnos.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


# ── Fixture ────────────────────────────────────────────────────────────────────


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
async def padron_db(db_session: AsyncSession) -> dict:
    """Seed for padron tests.

    Tenant A: coord (scope=all), prof (scope=own), noperm, alumno_existente,
              materia_a (no moodle_course_id), materia_a2 (moodle_course_id='42'),
              cohorte_a / cohorte_a2.
    Tenant B: coord_b, materia_b, cohorte_b.
    """
    # Cleanup in FK dependency order (calificacion before asignacion for FK)
    await db_session.execute(text("DELETE FROM calificacion"))
    await db_session.execute(text("DELETE FROM umbral_materia"))
    await db_session.execute(text("DELETE FROM entrada_padron"))
    await db_session.execute(text("DELETE FROM version_padron"))
    await db_session.execute(text("DELETE FROM asignacion"))
    await db_session.execute(text("DELETE FROM audit_log"))
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

    # ── Tenant A ──────────────────────────────────────────────────────────────
    tenant_a = Tenant(codigo=TENANT_CODE_A, nombre="Padrón Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    coord = _make_user(COORD_EMAIL, tid_a)
    prof = _make_user(PROF_EMAIL, tid_a)
    noperm = _make_user(NOPERM_EMAIL, tid_a)
    alumno_existente = _make_user(ALUMNO_EXISTENTE_EMAIL, tid_a)
    db_session.add_all([coord, prof, noperm, alumno_existente])
    await db_session.flush()
    for u in (coord, prof, noperm, alumno_existente):
        await db_session.refresh(u)

    rol_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    rol_prof = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    rol_noperm = Rol(tenant_id=tid_a, nombre="NEXO", descripcion="Sin permisos padron")
    db_session.add_all([rol_coord, rol_prof, rol_noperm])
    await db_session.flush()
    for r in (rol_coord, rol_prof, rol_noperm):
        await db_session.refresh(r)

    p_cargar = Permiso(tenant_id=tid_a, codigo="padron:cargar", modulo="padron", descripcion="Cargar")
    p_ver = Permiso(tenant_id=tid_a, codigo="padron:ver", modulo="padron", descripcion="Ver")
    db_session.add_all([p_cargar, p_ver])
    await db_session.flush()
    await db_session.refresh(p_cargar)
    await db_session.refresh(p_ver)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord.id, permiso_id=p_cargar.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord.id, permiso_id=p_ver.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_prof.id, permiso_id=p_cargar.id, scope="own"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_prof.id, permiso_id=p_ver.id, scope="own"),
        UserRol(tenant_id=tid_a, user_id=coord.id, rol_id=rol_coord.id),
        UserRol(tenant_id=tid_a, user_id=prof.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid_a, user_id=noperm.id, rol_id=rol_noperm.id),
    ])
    await db_session.flush()

    # Academic structure — Tenant A
    carrera_a = Carrera(tenant_id=tid_a, codigo="ING", nombre="Ingeniería")
    db_session.add(carrera_a)
    await db_session.flush()
    await db_session.refresh(carrera_a)

    cohorte_a = Cohorte(
        tenant_id=tid_a, carrera_id=carrera_a.id, nombre="2026-1",
        anio=2026, vig_desde=date(2026, 1, 1),
    )
    cohorte_a2 = Cohorte(
        tenant_id=tid_a, carrera_id=carrera_a.id, nombre="2026-2",
        anio=2026, vig_desde=date(2026, 7, 1),
    )
    db_session.add_all([cohorte_a, cohorte_a2])
    await db_session.flush()
    await db_session.refresh(cohorte_a)
    await db_session.refresh(cohorte_a2)

    materia_a = Materia(tenant_id=tid_a, codigo="MAT101", nombre="Matemática I")
    materia_a2 = Materia(
        tenant_id=tid_a, codigo="MAT102", nombre="Matemática II",
        moodle_course_id="42",
    )
    db_session.add_all([materia_a, materia_a2])
    await db_session.flush()
    await db_session.refresh(materia_a)
    await db_session.refresh(materia_a2)

    # ── Tenant B ──────────────────────────────────────────────────────────────
    tenant_b = Tenant(codigo=TENANT_CODE_B, nombre="Padrón Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    coord_b = _make_user(COORD_B_EMAIL, tid_b)
    db_session.add(coord_b)
    await db_session.flush()
    await db_session.refresh(coord_b)

    rol_coord_b = Rol(tenant_id=tid_b, nombre="COORDINADOR", descripcion="Coordinador B")
    db_session.add(rol_coord_b)
    await db_session.flush()
    await db_session.refresh(rol_coord_b)

    p_cargar_b = Permiso(tenant_id=tid_b, codigo="padron:cargar", modulo="padron", descripcion="Cargar")
    p_ver_b = Permiso(tenant_id=tid_b, codigo="padron:ver", modulo="padron", descripcion="Ver")
    db_session.add_all([p_cargar_b, p_ver_b])
    await db_session.flush()
    await db_session.refresh(p_cargar_b)
    await db_session.refresh(p_ver_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_coord_b.id, permiso_id=p_cargar_b.id, scope="all"),
        RolPermiso(tenant_id=tid_b, rol_id=rol_coord_b.id, permiso_id=p_ver_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=coord_b.id, rol_id=rol_coord_b.id),
    ])
    await db_session.flush()

    carrera_b = Carrera(tenant_id=tid_b, codigo="BIO", nombre="Biología")
    db_session.add(carrera_b)
    await db_session.flush()
    await db_session.refresh(carrera_b)

    cohorte_b = Cohorte(
        tenant_id=tid_b, carrera_id=carrera_b.id, nombre="2026-1",
        anio=2026, vig_desde=date(2026, 1, 1),
    )
    materia_b = Materia(tenant_id=tid_b, codigo="BIO101", nombre="Biología I")
    db_session.add_all([cohorte_b, materia_b])
    await db_session.flush()
    await db_session.refresh(cohorte_b)
    await db_session.refresh(materia_b)

    await db_session.commit()

    return {
        "tid_a": tid_a,
        "tid_b": tid_b,
        "coord_id": coord.id,
        "prof_id": prof.id,
        "alumno_existente_email": ALUMNO_EXISTENTE_EMAIL,
        "materia_a_id": materia_a.id,
        "materia_a2_id": materia_a2.id,
        "cohorte_a_id": cohorte_a.id,
        "cohorte_a2_id": cohorte_a2.id,
        "materia_b_id": materia_b.id,
        "cohorte_b_id": cohorte_b.id,
    }


# ── URL helpers ────────────────────────────────────────────────────────────────


def _url(mid: UUID, cid: UUID, suffix: str = "") -> str:
    return f"/api/v1/padron/{mid}/cohortes/{cid}{suffix}"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── TestImportArchivo ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestImportArchivo:
    async def test_import_xlsx_ok_201(self, async_client: AsyncClient, padron_db: dict) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(),
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["total_importadas"] == 3
        assert data["version"]["activa"] is True
        assert data["version"]["materia_id"] == str(d["materia_a_id"])

    async def test_import_csv_ok_201(self, async_client: AsyncClient, padron_db: dict) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        content = _make_csv(SAMPLE_ROWS)
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files={"file": ("alumnos.csv", content, "text/csv")},
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["total_importadas"] == 3

    async def test_preview_true_200_no_escribe_db(
        self, async_client: AsyncClient, padron_db: dict, db_session: AsyncSession
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar") + "?preview=true",
            files=_xlsx_files(),
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] == 3
        assert "entradas" in data

        # Verify DB was NOT written
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM version_padron WHERE tenant_id = :tid"),
            {"tid": d["tid_a"]},
        )
        assert result.scalar() == 0

    async def test_archivo_tipo_invalido_400(self, async_client: AsyncClient, padron_db: dict) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files={"file": ("data.txt", b"col1,col2\n1,2", "text/plain")},
            headers=_auth(token),
        )
        assert resp.status_code == 400

    async def test_csv_sin_columna_email_400(self, async_client: AsyncClient, padron_db: dict) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        content = b"nombre,apellidos\nAna,Garcia\n"
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files={"file": ("alumnos.csv", content, "text/csv")},
            headers=_auth(token),
        )
        assert resp.status_code == 400

    async def test_autolink_usuario_existente(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        rows = [
            {"nombre": "Alumno", "apellidos": "Existente", "email": d["alumno_existente_email"]},
            {"nombre": "Nuevo", "apellidos": "Sin Cuenta", "email": "nuevo@test.edu"},
        ]
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(rows),
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["entradas_vinculadas"] == 1
        assert data["total_importadas"] == 2

    async def test_autolink_no_cruza_tenants(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        # COORD_B_EMAIL exists in Tenant B only — must NOT be linked in Tenant A import
        rows = [{"nombre": "Coord", "apellidos": "B", "email": COORD_B_EMAIL}]
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(rows),
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["entradas_vinculadas"] == 0

    async def test_advertencia_fila_sin_nombre(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        rows = [
            {"nombre": "", "apellidos": "Sin nombre", "email": "x@test.edu"},
            {"nombre": "OK", "apellidos": "User", "email": "ok@test.edu"},
        ]
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(rows),
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["total_importadas"] == 1
        assert len(data["advertencias"]) >= 1


# ── TestVersionado ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestVersionado:
    async def _import(
        self, client: AsyncClient, d: dict, *, token: str, rows: list[dict] | None = None
    ) -> dict:
        resp = await client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(rows),
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text
        return resp.json()

    async def test_segunda_carga_desactiva_primera(
        self, async_client: AsyncClient, padron_db: dict, db_session: AsyncSession
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        r1 = await self._import(async_client, d, token=token)
        v1_id = r1["version"]["id"]

        r2 = await self._import(async_client, d, token=token, rows=[
            {"nombre": "Nuevo", "apellidos": "Alumno", "email": "nuevo2@test.edu"},
        ])
        v2_id = r2["version"]["id"]
        assert v1_id != v2_id

        from app.models.version_padron import VersionPadron  # noqa: PLC0415
        result = await db_session.execute(
            select(VersionPadron).where(VersionPadron.id == v1_id)
        )
        v1 = result.scalar_one()
        assert v1.activa is False

    async def test_get_version_activa_200(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        await self._import(async_client, d, token=token)
        resp = await async_client.get(
            _url(d["materia_a_id"], d["cohorte_a_id"]),
            headers=_auth(token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["version"]["activa"] is True
        assert len(data["entradas"]) == 3

    async def test_get_sin_version_activa_404(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        resp = await async_client.get(
            _url(d["materia_a_id"], d["cohorte_a_id"]),
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_get_muestra_email_plaintext(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        rows = [{"nombre": "Ana", "apellidos": "García", "email": "ana@plaintext.edu"}]
        await self._import(async_client, d, token=token, rows=rows)
        resp = await async_client.get(
            _url(d["materia_a_id"], d["cohorte_a_id"]),
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["entradas"][0]["email"] == "ana@plaintext.edu"


# ── TestPIICifrado ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPIICifrado:
    async def test_email_cifrado_en_db_plaintext_en_response(
        self, async_client: AsyncClient, padron_db: dict, db_session: AsyncSession
    ) -> None:
        d = padron_db
        target_email = "pii.test@test.edu"
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        rows = [{"nombre": "PII", "apellidos": "Test", "email": target_email}]
        import_resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(rows),
            headers=_auth(token),
        )
        assert import_resp.status_code == 201, import_resp.text

        # DB stores ciphertext (not plaintext)
        db_row = (await db_session.execute(
            text("SELECT email_cifrado, email_hash FROM entrada_padron WHERE tenant_id = :tid LIMIT 1"),
            {"tid": d["tid_a"]},
        )).one()
        assert db_row.email_cifrado != target_email
        assert db_row.email_hash == hmac_email(target_email)

        # API response has plaintext
        get_resp = await async_client.get(
            _url(d["materia_a_id"], d["cohorte_a_id"]),
            headers=_auth(token),
        )
        assert get_resp.json()["entradas"][0]["email"] == target_email


# ── TestVaciar ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestVaciar:
    async def _import(self, client: AsyncClient, d: dict, *, token: str) -> None:
        resp = await client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(),
            headers=_auth(token),
        )
        assert resp.status_code == 201, resp.text

    async def test_vaciar_como_coordinador_204(
        self, async_client: AsyncClient, padron_db: dict, db_session: AsyncSession
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        await self._import(async_client, d, token=token)
        resp = await async_client.delete(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/vaciar"),
            headers=_auth(token),
        )
        assert resp.status_code == 204, resp.text

        from app.models.version_padron import VersionPadron  # noqa: PLC0415
        result = await db_session.execute(
            select(VersionPadron).where(VersionPadron.tenant_id == d["tid_a"])
        )
        versions = result.scalars().all()
        assert len(versions) == 1
        assert versions[0].activa is False
        assert versions[0].deleted_at is not None

    async def test_vaciar_propio_como_profesor_204(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token_prof = await _login(async_client, TENANT_CODE_A, PROF_EMAIL)
        await self._import(async_client, d, token=token_prof)
        resp = await async_client.delete(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/vaciar"),
            headers=_auth(token_prof),
        )
        assert resp.status_code == 204

    async def test_vaciar_ajeno_como_profesor_403(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token_coord = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        token_prof = await _login(async_client, TENANT_CODE_A, PROF_EMAIL)
        # COORD imports — PROFESOR tries to vaciar (scope=own but version is COORD's)
        await self._import(async_client, d, token=token_coord)
        resp = await async_client.delete(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/vaciar"),
            headers=_auth(token_prof),
        )
        assert resp.status_code == 403

    async def test_vaciar_sin_version_activa_404(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        resp = await async_client.delete(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/vaciar"),
            headers=_auth(token),
        )
        assert resp.status_code == 404

    async def test_entradas_en_db_tras_vaciar_audit_trail(
        self, async_client: AsyncClient, padron_db: dict, db_session: AsyncSession
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        await self._import(async_client, d, token=token)
        await async_client.delete(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/vaciar"),
            headers=_auth(token),
        )
        # EntradaPadron rows must still exist (audit trail)
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM entrada_padron WHERE tenant_id = :tid"),
            {"tid": d["tid_a"]},
        )
        assert result.scalar() == 3


# ── TestRBAC ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestRBAC:
    async def test_sin_permiso_padron_cargar_403(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, NOPERM_EMAIL)
        resp = await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(),
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_sin_permiso_padron_ver_403(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token = await _login(async_client, TENANT_CODE_A, NOPERM_EMAIL)
        resp = await async_client.get(
            _url(d["materia_a_id"], d["cohorte_a_id"]),
            headers=_auth(token),
        )
        assert resp.status_code == 403

    async def test_tenant_isolation_coord_b_no_ve_datos_de_a(
        self, async_client: AsyncClient, padron_db: dict
    ) -> None:
        d = padron_db
        token_coord = await _login(async_client, TENANT_CODE_A, COORD_EMAIL)
        token_coord_b = await _login(async_client, TENANT_CODE_B, COORD_B_EMAIL)

        # Coord A imports into materia A
        await async_client.post(
            _url(d["materia_a_id"], d["cohorte_a_id"], "/importar"),
            files=_xlsx_files(),
            headers=_auth(token_coord),
        )
        # Coord B GET on materia A IDs → 404 (wrong tenant scope)
        resp = await async_client.get(
            _url(d["materia_a_id"], d["cohorte_a_id"]),
            headers=_auth(token_coord_b),
        )
        assert resp.status_code == 404
