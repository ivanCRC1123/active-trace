"""C-07 usuarios — integration tests.

Covers:
- ABM completo de Usuario (CRUD + soft-delete)
- Unicidad de email por tenant (409 en duplicados, OK en otro tenant)
- Aislamiento multi-tenant (404 cross-tenant)
- PII: email y campos sensibles cifrados en DB, plaintext en respuesta
- Bloqueo de delete cuando tiene asignaciones vigentes (400)
- RBAC: sin permiso → 403
"""

import uuid
from datetime import date, timedelta

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

TENANT_CODE = "usr-test-a"
OTHER_TENANT_CODE = "usr-test-b"
USER_PASS = "Admin123!"
ADMIN_EMAIL = "usr.admin@test.edu.ar"
COORD_EMAIL = "usr.coord@test.edu.ar"
ADMIN_B_EMAIL = "usr.admin.b@test.edu.ar"


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def usuario_db(db_session: AsyncSession) -> dict:
    """Seed two tenants: A with admin (has usuarios:gestionar) + coord (no perm), B with admin."""
    # Clean slate (reverse FK order)
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
            apellidos="User",
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
        )

    # Tenant A
    tenant_a = Tenant(codigo=TENANT_CODE, nombre="Usuarios Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    admin_a = _user(ADMIN_EMAIL, tid_a)
    coord = _user(COORD_EMAIL, tid_a)
    db_session.add_all([admin_a, coord])
    await db_session.flush()
    await db_session.refresh(admin_a)
    await db_session.refresh(coord)

    rol_admin_a = Rol(tenant_id=tid_a, nombre="ADMIN", descripcion="Admin")
    rol_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    db_session.add_all([rol_admin_a, rol_coord])
    await db_session.flush()
    await db_session.refresh(rol_admin_a)
    await db_session.refresh(rol_coord)

    p_usr = Permiso(
        tenant_id=tid_a,
        codigo="usuarios:gestionar",
        modulo="usuarios",
        descripcion="Gestionar usuarios",
    )
    db_session.add(p_usr)
    await db_session.flush()
    await db_session.refresh(p_usr)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin_a.id, permiso_id=p_usr.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=admin_a.id, rol_id=rol_admin_a.id),
        UserRol(tenant_id=tid_a, user_id=coord.id, rol_id=rol_coord.id),
    ])
    await db_session.flush()

    # Tenant B
    tenant_b = Tenant(codigo=OTHER_TENANT_CODE, nombre="Usuarios Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    admin_b = _user(ADMIN_B_EMAIL, tid_b)
    db_session.add(admin_b)
    await db_session.flush()
    await db_session.refresh(admin_b)

    rol_admin_b = Rol(tenant_id=tid_b, nombre="ADMIN", descripcion="Admin")
    db_session.add(rol_admin_b)
    await db_session.flush()
    await db_session.refresh(rol_admin_b)

    p_usr_b = Permiso(
        tenant_id=tid_b,
        codigo="usuarios:gestionar",
        modulo="usuarios",
        descripcion="Gestionar usuarios",
    )
    db_session.add(p_usr_b)
    await db_session.flush()
    await db_session.refresh(p_usr_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_admin_b.id, permiso_id=p_usr_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=admin_b.id, rol_id=rol_admin_b.id),
    ])
    await db_session.flush()
    await db_session.commit()

    return {
        "tenant_a_id": tid_a,
        "tenant_b_id": tid_b,
        "admin_a_id": admin_a.id,
        "coord_id": coord.id,
        "admin_b_id": admin_b.id,
    }


async def _login(client: AsyncClient, tenant_code: str, email: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"tenant_code": tenant_code, "email": email, "password": USER_PASS},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


# ── TestUsuarioABM ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUsuarioABM:
    async def test_create_ok(self, async_client, usuario_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/admin/usuarios",
            json={
                "nombre": "Maria",
                "apellidos": "Lopez",
                "email": "m.lopez@nuevo.edu.ar",
                "password": "Pass123!",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["nombre"] == "Maria"
        assert body["apellidos"] == "Lopez"
        assert body["email"] == "m.lopez@nuevo.edu.ar"
        assert body["estado"] == "Activo"
        assert "id" in body
        assert "tenant_id" in body

    async def test_create_email_duplicado_409(self, async_client, usuario_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"nombre": "X", "apellidos": "Y", "email": "dup@test.edu.ar", "password": "Pass123!"}
        await async_client.post("/api/v1/admin/usuarios", json=payload, headers=headers)
        resp = await async_client.post("/api/v1/admin/usuarios", json=payload, headers=headers)
        assert resp.status_code == 409

    async def test_create_email_otro_tenant_ok(self, async_client, usuario_db):
        """Same email in different tenant → 201 (tenant isolation)."""
        token_a = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        payload = {"nombre": "X", "apellidos": "Y", "email": "same@test.edu.ar", "password": "Pass123!"}
        r_a = await async_client.post(
            "/api/v1/admin/usuarios", json=payload, headers={"Authorization": f"Bearer {token_a}"}
        )
        r_b = await async_client.post(
            "/api/v1/admin/usuarios", json=payload, headers={"Authorization": f"Bearer {token_b}"}
        )
        assert r_a.status_code == 201
        assert r_b.status_code == 201

    async def test_list_solo_tenant_propio(self, async_client, usuario_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        await async_client.post(
            "/api/v1/admin/usuarios",
            json={"nombre": "A", "apellidos": "B", "email": "list.a@test.edu.ar", "password": "Pass!"},
            headers=headers,
        )
        resp = await async_client.get("/api/v1/admin/usuarios", headers=headers)
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "list.a@test.edu.ar" in emails
        # Tenant B's admin email must NOT appear
        assert ADMIN_B_EMAIL not in emails

    async def test_get_ok(self, async_client, usuario_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = await async_client.post(
            "/api/v1/admin/usuarios",
            json={"nombre": "G", "apellidos": "H", "email": "get.me@test.edu.ar", "password": "Pass!"},
            headers=headers,
        )
        uid = created.json()["id"]
        resp = await async_client.get(f"/api/v1/admin/usuarios/{uid}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "get.me@test.edu.ar"

    async def test_get_otro_tenant_404(self, async_client, usuario_db):
        """GET user from different tenant → 404."""
        token_b = await _login(async_client, OTHER_TENANT_CODE, ADMIN_B_EMAIL)
        admin_a_id = usuario_db["admin_a_id"]
        resp = await async_client.get(
            f"/api/v1/admin/usuarios/{admin_a_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404

    async def test_update_ok(self, async_client, usuario_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = await async_client.post(
            "/api/v1/admin/usuarios",
            json={"nombre": "Old", "apellidos": "Name", "email": "upd@test.edu.ar", "password": "Pass!"},
            headers=headers,
        )
        uid = created.json()["id"]
        resp = await async_client.patch(
            f"/api/v1/admin/usuarios/{uid}",
            json={"nombre": "New", "estado": "Inactivo"},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["nombre"] == "New"
        assert body["estado"] == "Inactivo"

    async def test_soft_delete_204_luego_get_404(self, async_client, usuario_db):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = await async_client.post(
            "/api/v1/admin/usuarios",
            json={"nombre": "Del", "apellidos": "Me", "email": "del@test.edu.ar", "password": "Pass!"},
            headers=headers,
        )
        uid = created.json()["id"]
        resp = await async_client.delete(f"/api/v1/admin/usuarios/{uid}", headers=headers)
        assert resp.status_code == 204
        resp2 = await async_client.get(f"/api/v1/admin/usuarios/{uid}", headers=headers)
        assert resp2.status_code == 404

    async def test_sin_permiso_403(self, async_client, usuario_db):
        token = await _login(async_client, TENANT_CODE, COORD_EMAIL)
        resp = await async_client.get(
            "/api/v1/admin/usuarios",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# ── TestPIICifrado ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestPIICifrado:
    async def test_email_cifrado_en_db_plaintext_en_respuesta(self, async_client, usuario_db, db_session):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        resp = await async_client.post(
            "/api/v1/admin/usuarios",
            json={
                "nombre": "PII",
                "apellidos": "Test",
                "email": "pii.check@test.edu.ar",
                "password": "Pass123!",
                "dni": "12345678",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        uid = resp.json()["id"]
        assert resp.json()["email"] == "pii.check@test.edu.ar"
        assert resp.json()["dni"] == "12345678"

        # Verify DB stores ciphertext (not plaintext)
        chk = await db_session.execute(
            text('SELECT email_cifrado, dni_cifrado FROM "user" WHERE id = :id'),
            {"id": uid},
        )
        row = chk.one()
        assert row.email_cifrado != "pii.check@test.edu.ar"
        assert row.dni_cifrado != "12345678"

    async def test_pii_update_cifrado_en_db(self, async_client, usuario_db, db_session):
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}
        created = await async_client.post(
            "/api/v1/admin/usuarios",
            json={"nombre": "PII", "apellidos": "Upd", "email": "pii.upd@test.edu.ar", "password": "Pass!"},
            headers=headers,
        )
        uid = created.json()["id"]
        resp = await async_client.patch(
            f"/api/v1/admin/usuarios/{uid}",
            json={"cbu": "0123456789012345678901"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["cbu"] == "0123456789012345678901"
        chk = await db_session.execute(
            text('SELECT cbu_cifrado FROM "user" WHERE id = :id'), {"id": uid}
        )
        assert chk.one().cbu_cifrado != "0123456789012345678901"


# ── TestDeleteConAsignacion ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDeleteConAsignacion:
    async def test_delete_con_asignacion_vigente_400(self, async_client, usuario_db, db_session):
        """DELETE usuario with active asignacion → 400."""
        token = await _login(async_client, TENANT_CODE, ADMIN_EMAIL)
        headers = {"Authorization": f"Bearer {token}"}

        # Create target user
        created = await async_client.post(
            "/api/v1/admin/usuarios",
            json={"nombre": "Blocked", "apellidos": "Del", "email": "blocked@test.edu.ar", "password": "Pass!"},
            headers=headers,
        )
        uid = created.json()["id"]

        # Create a rol to assign
        rol = Rol(tenant_id=usuario_db["tenant_a_id"], nombre="PROFESOR", descripcion="Prof")
        db_session.add(rol)
        await db_session.flush()
        await db_session.refresh(rol)

        # Insert active asignacion directly (bypassing service for setup brevity)
        today = date.today()
        await db_session.execute(
            text("""
                INSERT INTO asignacion (tenant_id, usuario_id, rol_id, desde, comisiones)
                VALUES (:tid, :uid, :rid, :desde, '[]'::json)
            """),
            {"tid": usuario_db["tenant_a_id"], "uid": uid, "rid": rol.id, "desde": today},
        )
        await db_session.commit()

        resp = await async_client.delete(f"/api/v1/admin/usuarios/{uid}", headers=headers)
        assert resp.status_code == 400
        assert "asignaciones vigentes" in resp.json()["detail"].lower()
