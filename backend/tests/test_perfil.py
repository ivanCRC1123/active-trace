"""C-20 perfil propio — tests de integración (F11.1).

Cubre:
- GET /api/v1/perfil: retorna perfil del usuario autenticado
- PATCH /api/v1/perfil: edita campos permitidos, rechaza campos restringidos
- Email: dual-write cifrado+hash, unicidad en tenant, no-op si mismo email
- PII: no aparece en AuditLog detalle; en DB queda cifrado, en response plaintext
- CUIL: inmodificable vía perfil (extra='forbid' en schema)
- Audit: PERFIL_ACTUALIZAR generado con campos_modificados
- Aislamiento multi-tenant
"""

from __future__ import annotations

from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import hmac_email
from app.core.security import create_access_token, hash_password
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_A = "perf-test-a"
TENANT_B = "perf-test-b"
USER_PASS = "Test123!"


# ── Fixture ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def perf_db(db_session: AsyncSession) -> dict:
    """Dos tenants, un usuario en cada uno. Sin permisos especiales (solo autenticado)."""
    await db_session.execute(text("TRUNCATE TABLE audit_log"))
    await db_session.execute(text("DELETE FROM asignacion"))
    await db_session.execute(text("DELETE FROM user_rol"))
    await db_session.execute(text("DELETE FROM rol_permiso"))
    await db_session.execute(text("DELETE FROM permiso"))
    await db_session.execute(text("DELETE FROM rol"))
    await db_session.execute(text("DELETE FROM refresh_token"))
    await db_session.execute(text("DELETE FROM recovery_token"))
    await db_session.execute(text('DELETE FROM "user"'))
    await db_session.execute(text("DELETE FROM tenant"))
    await db_session.commit()

    # Tenant A
    tenant_a = Tenant(codigo=TENANT_A, nombre="Perfil Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    # Tenant B
    tenant_b = Tenant(codigo=TENANT_B, nombre="Perfil Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    def _user(email: str, tid, nombre="Test", apellidos="User") -> User:
        # Pasamos plaintext: el EncryptedString TypeDecorator cifra en process_bind_param.
        # NO pre-encriptar o el flush doble-encripta y el SELECT devuelve ciphertext.
        return User(
            email_cifrado=email,
            email_hash=hmac_email(email),
            password_hash=hash_password(USER_PASS),
            nombre=nombre,
            apellidos=apellidos,
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
            cuil_cifrado="20-11111111-0",
            cbu_cifrado="0720461188000099999999",
        )

    user_a = _user("prof.a@test.edu.ar", tid_a, "Ana", "García")
    user_b = _user("prof.b@test.edu.ar", tid_b, "Bob", "Smith")
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    await db_session.refresh(user_a)
    await db_session.refresh(user_b)

    # Usuario extra en tenant A para test de unicidad de email
    user_a2 = _user("otro.a@test.edu.ar", tid_a, "Otro", "Usuario")
    db_session.add(user_a2)
    await db_session.flush()
    await db_session.refresh(user_a2)

    await db_session.commit()

    return {
        "tid_a": tid_a,
        "tid_b": tid_b,
        "user_a": user_a,
        "user_a2": user_a2,
        "user_b": user_b,
    }


def _token(user_id: UUID, tenant_id: UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, roles=["PROFESOR"])


# ── GET /api/v1/perfil ───────────────────────────────────────────────────────


class TestGetPerfil:
    async def test_get_perfil_ok(self, async_client: AsyncClient, perf_db: dict) -> None:
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.get(
            "/api/v1/perfil",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["nombre"] == "Ana"
        assert body["apellidos"] == "García"
        assert body["id"] == str(user_a.id)
        assert body["tenant_id"] == str(perf_db["tid_a"])

    async def test_get_perfil_email_plaintext(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """El email retornado debe ser el plaintext, no el ciphertext."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.get(
            "/api/v1/perfil",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        email = r.json()["email"]
        assert "@" in email
        assert email == "prof.a@test.edu.ar"

    async def test_get_perfil_cuil_readonly(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """CUIL aparece en el response (visible) pero no puede editarse."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.get(
            "/api/v1/perfil",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["cuil"] == "20-11111111-0"

    async def test_get_perfil_sin_auth_401(self, async_client: AsyncClient, perf_db: dict) -> None:
        r = await async_client.get("/api/v1/perfil")
        assert r.status_code == 401


# ── PATCH /api/v1/perfil — campos básicos ────────────────────────────────────


class TestPatchPerfil:
    async def test_patch_nombre(
        self, async_client: AsyncClient, perf_db: dict, db_session: AsyncSession
    ) -> None:
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"nombre": "Nuevo Nombre"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["nombre"] == "Nuevo Nombre"

    async def test_patch_nombre_genera_audit(
        self, async_client: AsyncClient, perf_db: dict, db_session: AsyncSession
    ) -> None:
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        await async_client.patch(
            "/api/v1/perfil",
            json={"nombre": "Auditado"},
            headers={"Authorization": f"Bearer {token}"},
        )
        row = await db_session.execute(
            text("SELECT accion, detalle FROM audit_log ORDER BY fecha_hora DESC LIMIT 1")
        )
        r = row.one()
        assert r.accion == "PERFIL_ACTUALIZAR"
        assert "nombre" in r.detalle["campos_modificados"]

    async def test_patch_sexo(self, async_client: AsyncClient, perf_db: dict) -> None:
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"sexo": "Femenino"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["sexo"] == "Femenino"

    async def test_patch_datos_bancarios(
        self, async_client: AsyncClient, perf_db: dict, db_session: AsyncSession
    ) -> None:
        """Datos bancarios actualizables; PII no aparece en audit detalle."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"cbu": "0000003100012345678901", "banco": "Nación"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["cbu"] == "0000003100012345678901"
        assert r.json()["banco"] == "Nación"

        # PII nunca en detalle del AuditLog
        row = await db_session.execute(
            text("SELECT detalle FROM audit_log ORDER BY fecha_hora DESC LIMIT 1")
        )
        detalle = row.scalar_one()
        assert "cbu" in detalle["campos_modificados"]
        # Los valores nunca deben aparecer en el detalle
        assert "0000003100012345678901" not in str(detalle)

    async def test_patch_cuil_rechazado_422(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """cuil ausente del schema → extra='forbid' lo rechaza con 422."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"cuil": "20-99999999-0"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    async def test_patch_legajo_rechazado_422(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """legajo tampoco es editable por el usuario."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"legajo": "LEG-999"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    async def test_patch_sin_auth_401(self, async_client: AsyncClient, perf_db: dict) -> None:
        r = await async_client.patch("/api/v1/perfil", json={"nombre": "X"})
        assert r.status_code == 401


# ── PATCH /api/v1/perfil — email (dual-write + unicidad) ─────────────────────


class TestPatchEmail:
    async def test_patch_email_exitoso(
        self, async_client: AsyncClient, perf_db: dict, db_session: AsyncSession
    ) -> None:
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"email": "nuevo.email@test.edu.ar"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["email"] == "nuevo.email@test.edu.ar"

        # Verificar dual-write en DB
        row = await db_session.execute(
            text('SELECT email_cifrado, email_hash FROM "user" WHERE id = :uid'),
            {"uid": str(user_a.id)},
        )
        db_row = row.one()
        expected_hash = hmac_email("nuevo.email@test.edu.ar")
        assert db_row.email_hash == expected_hash

        # AuditLog con cambio_email flag
        audit_row = await db_session.execute(
            text("SELECT detalle FROM audit_log ORDER BY fecha_hora DESC LIMIT 1")
        )
        detalle = audit_row.scalar_one()
        assert "email" in detalle["campos_modificados"]
        assert detalle.get("cambio_email") is True

    async def test_patch_email_duplicado_409(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """Otro usuario del mismo tenant ya tiene ese email → 409."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"email": "otro.a@test.edu.ar"},   # email de user_a2
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 409

    async def test_patch_email_mismo_usuario_noop(
        self, async_client: AsyncClient, perf_db: dict, db_session: AsyncSession
    ) -> None:
        """Mismo email del propio usuario → 200 sin error, sin audit innecesario."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        hash_antes = (
            await db_session.execute(
                text('SELECT email_hash FROM "user" WHERE id = :uid'),
                {"uid": str(user_a.id)},
            )
        ).scalar_one()

        r = await async_client.patch(
            "/api/v1/perfil",
            json={"email": "prof.a@test.edu.ar"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

        hash_despues = (
            await db_session.execute(
                text('SELECT email_hash FROM "user" WHERE id = :uid'),
                {"uid": str(user_a.id)},
            )
        ).scalar_one()
        assert hash_antes == hash_despues

    async def test_patch_email_otro_tenant_ok(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """Email existente en TENANT-B no bloquea al usuario de TENANT-A."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        # "prof.b@test.edu.ar" pertenece a tenant B, no a tenant A
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"email": "prof.b@test.edu.ar"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    async def test_blind_index_consistente_post_cambio(
        self, async_client: AsyncClient, perf_db: dict, db_session: AsyncSession
    ) -> None:
        """E2E del blind-index: tras cambiar email, el hash nuevo matchea al usuario
        y el hash viejo ya no lo encuentra.

        Un bug que derive el hash del valor cifrado (en vez del plaintext) o
        que no recompute el hash pasaría test_patch_email_exitoso pero rompería
        el login del usuario después del cambio.
        """
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])

        old_email = "prof.a@test.edu.ar"
        new_email = "nuevo.blind@test.edu.ar"
        old_hash = hmac_email(old_email)
        new_hash = hmac_email(new_email)

        # Cambiar email
        r = await async_client.patch(
            "/api/v1/perfil",
            json={"email": new_email},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

        # Buscar por hash nuevo → debe encontrar al usuario
        row_nuevo = await db_session.execute(
            text('SELECT id FROM "user" WHERE email_hash = :h AND deleted_at IS NULL'),
            {"h": new_hash},
        )
        found = row_nuevo.scalar_one_or_none()
        assert found is not None, "El nuevo email_hash no matchea ningún usuario"
        assert str(found) == str(user_a.id)

        # Buscar por hash viejo → no debe encontrar al usuario
        row_viejo = await db_session.execute(
            text('SELECT id FROM "user" WHERE email_hash = :h AND deleted_at IS NULL'),
            {"h": old_hash},
        )
        not_found = row_viejo.scalar_one_or_none()
        assert not_found is None, "El viejo email_hash todavía matchea al usuario (blind-index roto)"


# ── PII cifrada en DB, plaintext en response ──────────────────────────────────


class TestPIIEncryption:
    async def test_cbu_cifrado_en_db(
        self, async_client: AsyncClient, perf_db: dict, db_session: AsyncSession
    ) -> None:
        """Después del PATCH, el cbu_cifrado en DB es ciphertext (no plaintext)."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        new_cbu = "1234560000012345678901"
        await async_client.patch(
            "/api/v1/perfil",
            json={"cbu": new_cbu},
            headers={"Authorization": f"Bearer {token}"},
        )
        row = await db_session.execute(
            text('SELECT cbu_cifrado FROM "user" WHERE id = :uid'),
            {"uid": str(user_a.id)},
        )
        cbu_cifrado = row.scalar_one()
        assert cbu_cifrado != new_cbu          # no es plaintext
        assert len(cbu_cifrado) > len(new_cbu) # es ciphertext base64

    async def test_cbu_plaintext_en_response(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """La respuesta del GET devuelve el CBU en plaintext."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.get(
            "/api/v1/perfil",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["cbu"] == "0720461188000099999999"


# ── Self-only y aislamiento multi-tenant ──────────────────────────────────────


class TestAislamiento:
    async def test_get_perfil_propio_no_ajeno(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """Un usuario solo puede ver su propio perfil (no hay forma de pedir el de otro)."""
        user_a = perf_db["user_a"]
        token = _token(user_a.id, perf_db["tid_a"])
        r = await async_client.get(
            "/api/v1/perfil",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        assert body["id"] == str(user_a.id)
        assert body["nombre"] == "Ana"    # no "Bob" del tenant B

    async def test_tenant_a_no_ve_tenant_b(
        self, async_client: AsyncClient, perf_db: dict
    ) -> None:
        """El JWT de tenant A no puede acceder a datos de tenant B."""
        user_b = perf_db["user_b"]
        # Token de tenant A pero user_id de tenant B → get_current_user falla (user no en tenant A)
        token_a_pero_user_b = create_access_token(
            user_id=user_b.id,
            tenant_id=perf_db["tid_a"],   # tenant incorrecto para ese user
            roles=["PROFESOR"],
        )
        r = await async_client.get(
            "/api/v1/perfil",
            headers={"Authorization": f"Bearer {token_a_pero_user_b}"},
        )
        assert r.status_code == 401
