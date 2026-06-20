"""C-10 calificaciones y umbral — integration + unit tests.

Covers:
- Parser: (Real) columns → numeric, other → textual, email detection
- _derive_aprobado: numeric vs umbral, textual vs set
- Import: preview, confirm with selected activities, upsert idempotent
- Umbral: upsert, default fallback, recalc on change
- Umbral isolation: changing one docente's umbral doesn't affect another
- Vaciar: own-scope (PROFESOR), all-scope (COORDINADOR), tenant isolation
- Tenant isolation: cross-tenant lookup → 404
- RBAC: missing permission → 403
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from uuid import UUID

import openpyxl
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
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
from app.models.version_padron import VersionPadron
from app.models.entrada_padron import EntradaPadron

# ── Constants ──────────────────────────────────────────────────────────────────

TENANT_CODE = "calificaciones-test"
USER_PASS = "Admin123!"
PROF_EMAIL = "cal.prof@test.edu.ar"
PROF2_EMAIL = "cal.prof2@test.edu.ar"
COORD_EMAIL = "cal.coord@test.edu.ar"
NOPERM_EMAIL = "cal.noperm@test.edu.ar"

ALUMNO_1_EMAIL = "alumno1@test.edu"
ALUMNO_2_EMAIL = "alumno2@test.edu"
ALUMNO_3_EMAIL = "alumno3@test.edu"

# ── File helpers ───────────────────────────────────────────────────────────────


def _make_grade_xlsx(
    rows: list[dict],
    extra_columns: list[str] | None = None,
) -> bytes:
    """Build an xlsx grade file mimicking Moodle export."""
    wb = openpyxl.Workbook()
    ws = wb.active
    # Standard headers + activity columns
    activity_cols = extra_columns or [
        "TP1 (Real)",
        "TP2 (Real)",
        "Foro participacion",
    ]
    headers = ["Nombre", "Apellidos", "Correo electrónico"] + activity_cols
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_grade_csv(rows: list[dict], extra_columns: list[str] | None = None) -> bytes:
    activity_cols = extra_columns or ["TP1 (Real)", "TP2 (Real)", "Foro participacion"]
    headers = ["Nombre", "Apellidos", "Correo electrónico"] + activity_cols
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow({h: row.get(h, "") for h in headers})
    return buf.getvalue().encode("utf-8")


SAMPLE_GRADE_ROWS = [
    {
        "Nombre": "Ana", "Apellidos": "García", "Correo electrónico": ALUMNO_1_EMAIL,
        "TP1 (Real)": "75.00", "TP2 (Real)": "50.00", "Foro participacion": "Satisfactorio",
    },
    {
        "Nombre": "Bob", "Apellidos": "López", "Correo electrónico": ALUMNO_2_EMAIL,
        "TP1 (Real)": "30.00", "TP2 (Real)": "90.00", "Foro participacion": "No satisfactorio",
    },
    {
        "Nombre": "Clara", "Apellidos": "Ruiz", "Correo electrónico": ALUMNO_3_EMAIL,
        "TP1 (Real)": "-", "TP2 (Real)": "", "Foro participacion": "Supera lo esperado",
    },
]


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text}"
    return resp.json()["access_token"]


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


# ── Fixture ────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def cal_db(db_session: AsyncSession) -> dict:
    """Seed DB for calificaciones tests.

    Tenant: COORDINADOR (scope=all), PROFESOR (scope=own), PROFESOR2 (scope=own),
            NOPERM (no calificaciones perms).
    Structure: materia_a, cohorte_a, carrera_a.
    Padron: 3 alumnos in active version.
    Asignaciones: prof → materia_a/cohorte_a, prof2 → materia_a/cohorte_a,
                  coord → materia_a/cohorte_a.
    """
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

    tenant = Tenant(codigo=TENANT_CODE, nombre="Calificaciones Test")
    db_session.add(tenant)
    await db_session.flush()
    await db_session.refresh(tenant)
    tid = tenant.id

    prof = _make_user(PROF_EMAIL, tid)
    prof2 = _make_user(PROF2_EMAIL, tid)
    coord = _make_user(COORD_EMAIL, tid)
    noperm = _make_user(NOPERM_EMAIL, tid)
    db_session.add_all([prof, prof2, coord, noperm])
    await db_session.flush()
    for u in (prof, prof2, coord, noperm):
        await db_session.refresh(u)

    rol_coord = Rol(tenant_id=tid, nombre="COORDINADOR", descripcion="Coordinador")
    rol_prof = Rol(tenant_id=tid, nombre="PROFESOR", descripcion="Profesor")
    rol_noperm = Rol(tenant_id=tid, nombre="NEXO", descripcion="Sin permisos")
    db_session.add_all([rol_coord, rol_prof, rol_noperm])
    await db_session.flush()
    for r in (rol_coord, rol_prof, rol_noperm):
        await db_session.refresh(r)

    p_importar = Permiso(tenant_id=tid, codigo="calificaciones:importar", modulo="calificaciones", descripcion="Importar")
    p_ver = Permiso(tenant_id=tid, codigo="calificaciones:ver", modulo="calificaciones", descripcion="Ver")
    db_session.add_all([p_importar, p_ver])
    await db_session.flush()
    await db_session.refresh(p_importar)
    await db_session.refresh(p_ver)

    db_session.add_all([
        RolPermiso(tenant_id=tid, rol_id=rol_coord.id, permiso_id=p_importar.id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_coord.id, permiso_id=p_ver.id, scope="all"),
        RolPermiso(tenant_id=tid, rol_id=rol_prof.id, permiso_id=p_importar.id, scope="own"),
        RolPermiso(tenant_id=tid, rol_id=rol_prof.id, permiso_id=p_ver.id, scope="own"),
        UserRol(tenant_id=tid, user_id=prof.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid, user_id=prof2.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid, user_id=coord.id, rol_id=rol_coord.id),
        UserRol(tenant_id=tid, user_id=noperm.id, rol_id=rol_noperm.id),
    ])
    await db_session.flush()

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

    materia = Materia(tenant_id=tid, codigo="PROG", nombre="Programación I", estado="Activa")
    db_session.add(materia)
    await db_session.flush()
    await db_session.refresh(materia)

    # Asignaciones for prof, prof2, coord → same materia+cohorte
    asig_prof = Asignacion(
        tenant_id=tid, usuario_id=prof.id, rol_id=rol_prof.id,
        materia_id=materia.id, cohorte_id=cohorte.id, carrera_id=carrera.id,
        desde=date(2026, 3, 1),
    )
    asig_prof2 = Asignacion(
        tenant_id=tid, usuario_id=prof2.id, rol_id=rol_prof.id,
        materia_id=materia.id, cohorte_id=cohorte.id, carrera_id=carrera.id,
        desde=date(2026, 3, 1),
    )
    asig_coord = Asignacion(
        tenant_id=tid, usuario_id=coord.id, rol_id=rol_coord.id,
        materia_id=materia.id, cohorte_id=cohorte.id, carrera_id=carrera.id,
        desde=date(2026, 3, 1),
    )
    db_session.add_all([asig_prof, asig_prof2, asig_coord])
    await db_session.flush()
    for a in (asig_prof, asig_prof2, asig_coord):
        await db_session.refresh(a)

    # Active padron with 3 alumnos
    version = VersionPadron(
        tenant_id=tid, materia_id=materia.id, cohorte_id=cohorte.id,
        cargado_por=prof.id, activa=True,
    )
    db_session.add(version)
    await db_session.flush()
    await db_session.refresh(version)

    alumnos_emails = [ALUMNO_1_EMAIL, ALUMNO_2_EMAIL, ALUMNO_3_EMAIL]
    for email in alumnos_emails:
        ep = EntradaPadron(
            tenant_id=tid, version_id=version.id,
            nombre="Alumno", apellidos="Test",
            email_cifrado=encrypt(email),
            email_hash=hmac_email(email),
        )
        db_session.add(ep)
    await db_session.flush()
    await db_session.commit()

    return {
        "tenant_id": str(tid),
        "materia_id": str(materia.id),
        "cohorte_id": str(cohorte.id),
        "carrera_id": str(carrera.id),
        "prof_id": str(prof.id),
        "prof2_id": str(prof2.id),
        "coord_id": str(coord.id),
        "asig_prof_id": str(asig_prof.id),
        "asig_prof2_id": str(asig_prof2.id),
        "asig_coord_id": str(asig_coord.id),
        "version_id": str(version.id),
    }


# ── Unit tests: parser ─────────────────────────────────────────────────────────


class TestCalificacionesParser:
    def test_detects_real_columns_as_numeric(self):
        from app.services.calificaciones_parser import parse_grade_file
        rows = [
            {"Correo electrónico": "a@b.com", "TP1 (Real)": "75", "Foro": "Satisfactorio"},
        ]
        content = _make_grade_xlsx(rows, extra_columns=["TP1 (Real)", "Foro"])
        parsed = parse_grade_file(content, "grades.xlsx")
        tipos = {a["nombre"]: a["tipo"] for a in parsed["actividades"]}
        assert tipos["TP1 (Real)"] == "numerica"
        assert tipos["Foro"] == "textual"

    def test_email_column_not_included_as_activity(self):
        from app.services.calificaciones_parser import parse_grade_file
        rows = [{"Correo electrónico": "a@b.com", "TP1 (Real)": "70"}]
        content = _make_grade_xlsx(rows, extra_columns=["TP1 (Real)"])
        parsed = parse_grade_file(content, "grades.xlsx")
        nombres = [a["nombre"] for a in parsed["actividades"]]
        assert "Correo electrónico" not in nombres
        assert "TP1 (Real)" in nombres

    def test_csv_parsed(self):
        from app.services.calificaciones_parser import parse_grade_file
        cols = ["TP1 (Real)", "Foro participacion"]
        rows = [{"Correo electrónico": "a@b.com", "TP1 (Real)": "80", "Foro participacion": "Satisfactorio"}]
        content = _make_grade_csv(rows, extra_columns=cols)
        parsed = parse_grade_file(content, "grades.csv")
        assert len(parsed["filas"]) == 1
        assert len(parsed["actividades"]) == 2

    def test_duplicate_email_warns_and_deduplicates(self):
        from app.services.calificaciones_parser import parse_grade_file
        rows = [
            {"Correo electrónico": "dup@test.com", "TP1 (Real)": "80"},
            {"Correo electrónico": "dup@test.com", "TP1 (Real)": "90"},
        ]
        content = _make_grade_xlsx(rows, extra_columns=["TP1 (Real)"])
        parsed = parse_grade_file(content, "grades.xlsx")
        assert len(parsed["filas"]) == 1
        assert any("duplicado" in w.lower() for w in parsed["warnings"])

    def test_unsupported_format_raises(self):
        from app.services.calificaciones_parser import parse_grade_file
        with pytest.raises(ValueError, match="no soportado"):
            parse_grade_file(b"data", "grades.pdf")


# ── Unit tests: _derive_aprobado ──────────────────────────────────────────────


class TestDeriveAprobado:
    def test_numeric_above_threshold(self):
        from app.repositories.calificacion_repository import _derive_aprobado
        assert _derive_aprobado(Decimal("75"), None, 60, []) is True

    def test_numeric_below_threshold(self):
        from app.repositories.calificacion_repository import _derive_aprobado
        assert _derive_aprobado(Decimal("50"), None, 60, []) is False

    def test_numeric_exactly_at_threshold(self):
        from app.repositories.calificacion_repository import _derive_aprobado
        assert _derive_aprobado(Decimal("60"), None, 60, []) is True

    def test_textual_in_approved_set(self):
        from app.repositories.calificacion_repository import _derive_aprobado
        assert _derive_aprobado(None, "Satisfactorio", 60, ["Satisfactorio", "Supera lo esperado"]) is True

    def test_textual_not_in_approved_set(self):
        from app.repositories.calificacion_repository import _derive_aprobado
        assert _derive_aprobado(None, "No satisfactorio", 60, ["Satisfactorio"]) is False

    def test_no_grade_is_not_aprobado(self):
        from app.repositories.calificacion_repository import _derive_aprobado
        assert _derive_aprobado(None, None, 60, ["Satisfactorio"]) is False

    def test_numeric_takes_priority_over_textual(self):
        from app.repositories.calificacion_repository import _derive_aprobado
        # If numeric is set, textual value should be ignored
        assert _derive_aprobado(Decimal("40"), "Satisfactorio", 60, ["Satisfactorio"]) is False


# ── Integration tests ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPreview:
    async def test_preview_detects_activities(self, async_client, cal_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        resp = await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/preview",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_alumnos"] == 3
        nombres = [a["nombre"] for a in data["actividades"]]
        assert "TP1 (Real)" in nombres
        assert "TP2 (Real)" in nombres
        assert "Foro participacion" in nombres

    async def test_preview_no_permission(self, async_client, cal_db):
        token = await _login(async_client, TENANT_CODE, NOPERM_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        resp = await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/preview",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestImport:
    async def test_import_creates_calificaciones(self, async_client, cal_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        resp = await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar"
            "?actividades_seleccionadas=TP1+%28Real%29&actividades_seleccionadas=Foro+participacion",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["importadas"] > 0
        assert data["omitidas"] == 0

    async def test_import_only_selected_activities(self, async_client, cal_db, db_session):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        # Only select TP1 (Real)
        resp = await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar"
            "?actividades_seleccionadas=TP1+%28Real%29",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.text
        from app.models.calificacion import Calificacion  # noqa: PLC0415
        from sqlalchemy import select as _select  # noqa: PLC0415
        rows = (await db_session.execute(
            _select(Calificacion).where(Calificacion.deleted_at.is_(None))
        )).scalars().all()
        actividades = {r.actividad for r in rows}
        assert actividades == {"TP1 (Real)"}

    async def test_import_upserts_on_reimport(self, async_client, cal_db, db_session):
        """Re-importing the same file updates existing records (actualizadas > 0)."""
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        params = "?actividades_seleccionadas=TP1+%28Real%29"
        file_args = {"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

        resp1 = await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar{params}",
            files=file_args,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 201
        importadas_1 = resp1.json()["importadas"]

        content2 = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        resp2 = await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar{params}",
            files={"file": ("grades.xlsx", content2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 201
        assert resp2.json()["actualizadas"] == importadas_1
        assert resp2.json()["importadas"] == 0

    async def test_import_aprobado_numeric(self, async_client, cal_db, db_session):
        """TP1 with nota=75 and default umbral=60 → aprobado=True."""
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar"
            "?actividades_seleccionadas=TP1+%28Real%29",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        from app.models.calificacion import Calificacion  # noqa: PLC0415
        rows = (await db_session.execute(
            select(Calificacion).where(
                Calificacion.actividad == "TP1 (Real)",
                Calificacion.deleted_at.is_(None),
            )
        )).scalars().all()
        # Ana: 75 >= 60 → True; Bob: 30 < 60 → False; Clara: no nota → False
        by_email = {}
        for r in rows:
            ep = (await db_session.get(EntradaPadron, r.entrada_padron_id))
            by_email[ep.email_hash] = r.aprobado

        assert by_email[hmac_email(ALUMNO_1_EMAIL)] is True
        assert by_email[hmac_email(ALUMNO_2_EMAIL)] is False
        assert by_email[hmac_email(ALUMNO_3_EMAIL)] is False

    async def test_import_aprobado_textual(self, async_client, cal_db, db_session):
        """Foro: 'Satisfactorio' → aprobado=True; 'No satisfactorio' → False."""
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar"
            "?actividades_seleccionadas=Foro+participacion",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        from app.models.calificacion import Calificacion  # noqa: PLC0415
        rows = (await db_session.execute(
            select(Calificacion).where(
                Calificacion.actividad == "Foro participacion",
                Calificacion.deleted_at.is_(None),
            )
        )).scalars().all()
        by_email = {}
        for r in rows:
            ep = (await db_session.get(EntradaPadron, r.entrada_padron_id))
            by_email[ep.email_hash] = r.aprobado

        assert by_email[hmac_email(ALUMNO_1_EMAIL)] is True   # Satisfactorio
        assert by_email[hmac_email(ALUMNO_2_EMAIL)] is False  # No satisfactorio
        assert by_email[hmac_email(ALUMNO_3_EMAIL)] is True   # Supera lo esperado

    async def test_import_no_permission(self, async_client, cal_db):
        token = await _login(async_client, TENANT_CODE, NOPERM_EMAIL)
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        resp = await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar"
            "?actividades_seleccionadas=TP1+%28Real%29",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestUmbral:
    async def test_get_umbral_default(self, async_client, cal_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.get(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/umbral",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["umbral_pct"] == 60
        assert data["es_default"] is True

    async def test_upsert_umbral(self, async_client, cal_db):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        resp = await async_client.put(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/umbral",
            json={"umbral_pct": 70, "valores_aprobatorios": ["Satisfactorio"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["umbral_pct"] == 70
        assert data["valores_aprobatorios"] == ["Satisfactorio"]
        assert data["es_default"] is False

    async def test_umbral_isolation_between_docentes(self, async_client, cal_db, db_session):
        """Changing prof's umbral does NOT affect prof2's threshold."""
        token_prof = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        token_prof2 = await _login(async_client, TENANT_CODE, PROF2_EMAIL)

        # Prof sets umbral to 80
        await async_client.put(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/umbral",
            json={"umbral_pct": 80, "valores_aprobatorios": ["Satisfactorio"]},
            headers={"Authorization": f"Bearer {token_prof}"},
        )

        # Prof2's umbral is still default
        resp2 = await async_client.get(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/umbral",
            headers={"Authorization": f"Bearer {token_prof2}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["umbral_pct"] == 60

    async def test_umbral_recalc_on_change(self, async_client, cal_db, db_session):
        """When umbral changes from 60 to 80, grades that were aprobado=True may flip."""
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)

        # Import TP1: Ana=75, Bob=30
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        await async_client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar"
            "?actividades_seleccionadas=TP1+%28Real%29",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )

        # With umbral=60: Ana (75) → aprobado=True
        from app.models.calificacion import Calificacion  # noqa: PLC0415
        db_session.expire_all()
        rows = (await db_session.execute(
            select(Calificacion).where(Calificacion.deleted_at.is_(None), Calificacion.actividad == "TP1 (Real)")
        )).scalars().all()
        ep_a1 = await db_session.get(EntradaPadron, next(r.entrada_padron_id for r in rows if True))
        # Find Ana's row
        ana_row = None
        for r in rows:
            ep = await db_session.get(EntradaPadron, r.entrada_padron_id)
            if ep.email_hash == hmac_email(ALUMNO_1_EMAIL):
                ana_row = r
                break
        assert ana_row is not None
        assert ana_row.aprobado is True
        ana_row_id = ana_row.id  # capture before expire invalidates the object

        # Change umbral to 80 → Ana (75 < 80) should flip to False
        await async_client.put(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/umbral",
            json={"umbral_pct": 80, "valores_aprobatorios": ["Satisfactorio", "Supera lo esperado"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        db_session.expire_all()
        ana_row_updated = await db_session.get(Calificacion, ana_row_id)
        assert ana_row_updated.aprobado is False


@pytest.mark.asyncio
class TestVaciar:
    async def _import_for_prof(self, client, token, cal_db) -> None:
        content = _make_grade_xlsx(SAMPLE_GRADE_ROWS)
        resp = await client.post(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/importar"
            "?actividades_seleccionadas=TP1+%28Real%29",
            files={"file": ("grades.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    async def test_prof_vaciar_own_data(self, async_client, cal_db, db_session):
        token = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        await self._import_for_prof(async_client, token, cal_db)

        resp = await async_client.delete(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/vaciar",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["eliminadas"] > 0

        # Verify soft-deleted
        from app.models.calificacion import Calificacion  # noqa: PLC0415
        count = len((await db_session.execute(
            select(Calificacion).where(Calificacion.deleted_at.is_(None))
        )).scalars().all())
        assert count == 0

    async def test_prof_vaciar_does_not_affect_other_prof(self, async_client, cal_db, db_session):
        """Prof vaciar only clears own data; prof2's calificaciones survive."""
        token_prof = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        token_prof2 = await _login(async_client, TENANT_CODE, PROF2_EMAIL)

        await self._import_for_prof(async_client, token_prof, cal_db)
        await self._import_for_prof(async_client, token_prof2, cal_db)

        # Count before: should be 6 (3 alumnos × 2 profs)
        from app.models.calificacion import Calificacion  # noqa: PLC0415
        db_session.expire_all()
        total_before = len((await db_session.execute(
            select(Calificacion).where(Calificacion.deleted_at.is_(None))
        )).scalars().all())
        assert total_before == 6

        # Prof vaciar own
        resp = await async_client.delete(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/vaciar",
            headers={"Authorization": f"Bearer {token_prof}"},
        )
        assert resp.status_code == 200
        assert resp.json()["eliminadas"] == 3

        db_session.expire_all()
        total_after = len((await db_session.execute(
            select(Calificacion).where(Calificacion.deleted_at.is_(None))
        )).scalars().all())
        assert total_after == 3  # prof2's data still alive

    async def test_coord_vaciar_all(self, async_client, cal_db, db_session):
        """COORDINADOR (scope=all) can vaciar all calificaciones for the materia."""
        token_prof = await _login(async_client, TENANT_CODE, PROF_EMAIL)
        token_coord = await _login(async_client, TENANT_CODE, COORD_EMAIL)

        await self._import_for_prof(async_client, token_prof, cal_db)

        resp = await async_client.delete(
            f"/api/v1/calificaciones/{cal_db['materia_id']}/cohortes/{cal_db['cohorte_id']}/vaciar",
            headers={"Authorization": f"Bearer {token_coord}"},
        )
        assert resp.status_code == 200
        assert resp.json()["eliminadas"] >= 3
