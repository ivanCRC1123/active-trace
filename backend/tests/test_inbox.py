"""C-20 mensajería interna — tests de integración (F11.2).

Cubre por propiedad:
- Self-scope del inbox: GET /inbox solo retorna hilos donde el usuario es participante
- Rechazo de no-participante: GET/{id} y POST/{id}/mensajes devuelven 403 si no participa
- Creación de hilo con participantes y mensaje inicial
- Mensaje del sistema: remitente_id NULL en DB, remitente_nombre NULL en response
- Aislamiento de tenant: hilo de tenant A invisible para usuario de tenant B
- PII no expuesta: email y cuil nunca aparecen en la response de inbox
- marcar_leido: actualiza ultimo_leido_at sin exponer PII
- Sin auth: 401 en todos los endpoints
"""

from __future__ import annotations

from uuid import UUID

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.core.encryption import hmac_email
from app.models.hilo_mensaje import HiloMensaje
from app.models.hilo_participante import HiloParticipante
from app.models.mensaje_interno import MensajeInterno
from app.models.tenant import Tenant
from app.models.user import User

TENANT_A = "inbox-test-a"
TENANT_B = "inbox-test-b"


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def inbox_db(db_session: AsyncSession) -> dict:
    """Dos tenants, dos usuarios en A, uno en B. Sin permisos especiales."""
    await db_session.execute(text("DELETE FROM mensaje_interno"))
    await db_session.execute(text("DELETE FROM hilo_participante"))
    await db_session.execute(text("DELETE FROM hilo_mensaje"))
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

    tenant_a = Tenant(codigo=TENANT_A, nombre="Inbox Test A")
    tenant_b = Tenant(codigo=TENANT_B, nombre="Inbox Test B")
    db_session.add_all([tenant_a, tenant_b])
    await db_session.flush()
    await db_session.refresh(tenant_a)
    await db_session.refresh(tenant_b)
    tid_a, tid_b = tenant_a.id, tenant_b.id

    def _user(email: str, tid: UUID, nombre: str, apellidos: str) -> User:
        return User(
            email_cifrado=email,
            email_hash=hmac_email(email),
            password_hash=hash_password("Test123!"),
            nombre=nombre,
            apellidos=apellidos,
            is_active=True,
            is_2fa_enabled=False,
            tenant_id=tid,
            cuil_cifrado="20-11111111-0",
        )

    user_a1 = _user("inbox.a1@test.edu.ar", tid_a, "Ana", "García")
    user_a2 = _user("inbox.a2@test.edu.ar", tid_a, "Bob", "López")
    user_b1 = _user("inbox.b1@test.edu.ar", tid_b, "Carlos", "Ruiz")
    db_session.add_all([user_a1, user_a2, user_b1])
    await db_session.flush()
    await db_session.refresh(user_a1)
    await db_session.refresh(user_a2)
    await db_session.refresh(user_b1)
    await db_session.commit()

    return {
        "tid_a": tid_a, "tid_b": tid_b,
        "user_a1": user_a1, "user_a2": user_a2, "user_b1": user_b1,
    }


def _token(user_id: UUID, tenant_id: UUID) -> str:
    return create_access_token(user_id=user_id, tenant_id=tenant_id, roles=["PROFESOR"])


def _auth(user: User, tenant_id: UUID) -> dict:
    return {"Authorization": f"Bearer {_token(user.id, tenant_id)}"}


# ── GET /api/v1/inbox — self-scope ────────────────────────────────────────────


class TestInboxListar:
    async def test_inbox_vacio_sin_hilos(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        r = await async_client.get(
            "/api/v1/inbox",
            headers=_auth(inbox_db["user_a1"], inbox_db["tid_a"]),
        )
        assert r.status_code == 200
        assert r.json() == []

    async def test_inbox_solo_hilos_propios(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        """user_a1 crea un hilo con user_a2. user_a2 ve el hilo; user_b1 no."""
        d = inbox_db
        # Crear hilo: a1 → a2
        r_crear = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Consulta", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Hola"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        assert r_crear.status_code == 201

        # a1 ve el hilo
        r_a1 = await async_client.get("/api/v1/inbox", headers=_auth(d["user_a1"], d["tid_a"]))
        assert r_a1.status_code == 200
        assert len(r_a1.json()) == 1
        assert r_a1.json()[0]["asunto"] == "Consulta"

        # a2 también es participante → ve el hilo
        r_a2 = await async_client.get("/api/v1/inbox", headers=_auth(d["user_a2"], d["tid_a"]))
        assert r_a2.status_code == 200
        assert len(r_a2.json()) == 1

    async def test_inbox_no_incluye_hilo_ajeno(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        """user_a1 crea un hilo solo entre a1 y a2. user_b1 no ve nada en su inbox."""
        d = inbox_db
        await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Solo A", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Privado"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        # b1 en su tenant no ve el hilo de tenant A
        r = await async_client.get("/api/v1/inbox", headers=_auth(d["user_b1"], d["tid_b"]))
        assert r.status_code == 200
        assert r.json() == []

    async def test_inbox_sin_auth_401(self, async_client: AsyncClient, inbox_db: dict) -> None:
        r = await async_client.get("/api/v1/inbox")
        assert r.status_code == 401


# ── POST /api/v1/inbox — crear hilo ──────────────────────────────────────────


class TestInboxCrear:
    async def test_crear_hilo_exitoso(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        d = inbox_db
        r = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Tema nuevo", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Primer msj"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["asunto"] == "Tema nuevo"
        assert len(body["mensajes"]) == 1
        assert body["mensajes"][0]["cuerpo"] == "Primer msj"
        assert body["mensajes"][0]["remitente_id"] == str(d["user_a1"].id)
        # Ambos participantes presentes
        ids_part = {p["usuario_id"] for p in body["participantes"]}
        assert str(d["user_a1"].id) in ids_part
        assert str(d["user_a2"].id) in ids_part

    async def test_crear_hilo_sin_auth_401(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "X", "destinatario_ids": [], "mensaje": "Y"},
        )
        assert r.status_code == 401


# ── GET /api/v1/inbox/{id} — detalle con access control ──────────────────────


class TestInboxGetHilo:
    async def _crear_hilo(self, client: AsyncClient, d: dict) -> str:
        r = await client.post(
            "/api/v1/inbox",
            json={"asunto": "Detalle", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Hola"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        return r.json()["id"]

    async def test_get_hilo_participante_ok(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        d = inbox_db
        hilo_id = await self._crear_hilo(async_client, d)
        r = await async_client.get(
            f"/api/v1/inbox/{hilo_id}",
            headers=_auth(d["user_a2"], d["tid_a"]),   # a2 es participante
        )
        assert r.status_code == 200
        assert r.json()["id"] == hilo_id

    async def test_get_hilo_no_participante_403(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        """user_b1 no participa en el hilo de tenant A → 403 aunque el hilo exista."""
        d = inbox_db
        hilo_id = await self._crear_hilo(async_client, d)
        # Usar token de tenant A pero con user_b1: simula un atacante con token válido
        # que intenta leer un hilo en el que no participa.
        # En la práctica, b1 ni siquiera está en tenant A, así que usamos a2 con otro hilo
        # para que exista pero sin participar.

        # Creamos un segundo hilo solo entre a1 y a1 (a2 no participa)
        r_hilo2 = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Secreto", "destinatario_ids": [], "mensaje": "Solo yo"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        hilo2_id = r_hilo2.json()["id"]

        # a2 intenta leer hilo2 donde NO es participante → 403
        r = await async_client.get(
            f"/api/v1/inbox/{hilo2_id}",
            headers=_auth(d["user_a2"], d["tid_a"]),
        )
        assert r.status_code == 403

    async def test_get_hilo_otro_tenant_404(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        """Un hilo de tenant A es invisible para tenant B → 404."""
        d = inbox_db
        hilo_id = await self._crear_hilo(async_client, d)
        r = await async_client.get(
            f"/api/v1/inbox/{hilo_id}",
            headers=_auth(d["user_b1"], d["tid_b"]),
        )
        assert r.status_code == 404

    async def test_get_hilo_sin_auth_401(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        d = inbox_db
        hilo_id = await self._crear_hilo(async_client, d)
        r = await async_client.get(f"/api/v1/inbox/{hilo_id}")
        assert r.status_code == 401


# ── POST /api/v1/inbox/{id}/mensajes — responder con access control ───────────


class TestInboxResponder:
    async def _crear_hilo(self, client: AsyncClient, d: dict) -> str:
        r = await client.post(
            "/api/v1/inbox",
            json={"asunto": "Respuesta", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Init"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        return r.json()["id"]

    async def test_responder_participante_ok(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        d = inbox_db
        hilo_id = await self._crear_hilo(async_client, d)
        r = await async_client.post(
            f"/api/v1/inbox/{hilo_id}/mensajes",
            json={"cuerpo": "Respuesta de a2"},
            headers=_auth(d["user_a2"], d["tid_a"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["cuerpo"] == "Respuesta de a2"
        assert body["remitente_id"] == str(d["user_a2"].id)
        assert body["remitente_nombre"] == "Bob"
        assert body["remitente_apellidos"] == "López"

    async def test_responder_no_participante_403(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        """Un usuario autenticado NO puede responder en un hilo del que no es parte."""
        d = inbox_db
        # Hilo entre a1 y a1 (a2 no participa)
        r_hilo = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Cerrado", "destinatario_ids": [], "mensaje": "Solo a1"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        hilo_id = r_hilo.json()["id"]

        r = await async_client.post(
            f"/api/v1/inbox/{hilo_id}/mensajes",
            json={"cuerpo": "Intruso"},
            headers=_auth(d["user_a2"], d["tid_a"]),  # a2 no participa
        )
        assert r.status_code == 403

    async def test_responder_sin_auth_401(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        d = inbox_db
        hilo_id = await self._crear_hilo(async_client, d)
        r = await async_client.post(f"/api/v1/inbox/{hilo_id}/mensajes", json={"cuerpo": "X"})
        assert r.status_code == 401


# ── Mensaje del sistema (remitente NULL) ──────────────────────────────────────


class TestMensajeSistema:
    async def test_mensaje_sistema_remitente_null(
        self, async_client: AsyncClient, inbox_db: dict, db_session: AsyncSession
    ) -> None:
        """Un MensajeInterno con remitente_id NULL se retorna sin nombre de remitente."""
        d = inbox_db
        # Crear hilo para tener un hilo_id válido
        r_hilo = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Sistema", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Init"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        hilo_id = r_hilo.json()["id"]

        # Insertar mensaje de sistema directamente (remitente_id NULL)
        await db_session.execute(
            text(
                "INSERT INTO mensaje_interno (tenant_id, hilo_id, remitente_id, cuerpo) "
                "VALUES (:tid, :hid, NULL, :cuerpo)"
            ),
            {"tid": str(d["tid_a"]), "hid": hilo_id, "cuerpo": "Aviso automático del sistema"},
        )
        await db_session.commit()

        # Leer el detalle del hilo
        r = await async_client.get(
            f"/api/v1/inbox/{hilo_id}",
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        assert r.status_code == 200
        mensajes = r.json()["mensajes"]
        sys_msgs = [m for m in mensajes if m["remitente_id"] is None]
        assert len(sys_msgs) == 1
        assert sys_msgs[0]["remitente_nombre"] is None
        assert sys_msgs[0]["remitente_apellidos"] is None
        assert sys_msgs[0]["cuerpo"] == "Aviso automático del sistema"


# ── PII no expuesta ───────────────────────────────────────────────────────────


class TestPIIInbox:
    async def test_respuesta_no_expone_email(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        """Ningún campo de la response de inbox contiene email ni cuil."""
        d = inbox_db
        r = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "PII check", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Test"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        body_str = str(r.json())
        assert "test.edu.ar" not in body_str       # no email en response
        assert "11111111" not in body_str           # no cuil en response

    async def test_participantes_solo_nombre_apellidos(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        d = inbox_db
        r = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Participantes", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Hola"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        hilo_id = r.json()["id"]
        r2 = await async_client.get(
            f"/api/v1/inbox/{hilo_id}",
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        for part in r2.json()["participantes"]:
            assert "email" not in part
            assert "cuil" not in part
            assert "nombre" in part
            assert "apellidos" in part


# ── marcar_leido ──────────────────────────────────────────────────────────────


class TestMarcarLeido:
    async def test_marcar_leido_participante(
        self, async_client: AsyncClient, inbox_db: dict, db_session: AsyncSession
    ) -> None:
        d = inbox_db
        r_hilo = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Leer", "destinatario_ids": [str(d["user_a2"].id)], "mensaje": "Init"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        hilo_id = r_hilo.json()["id"]

        r = await async_client.post(
            f"/api/v1/inbox/{hilo_id}/leer",
            headers=_auth(d["user_a2"], d["tid_a"]),
        )
        assert r.status_code == 204

        row = await db_session.execute(
            text(
                "SELECT ultimo_leido_at FROM hilo_participante "
                "WHERE hilo_id = :hid AND usuario_id = :uid"
            ),
            {"hid": hilo_id, "uid": str(d["user_a2"].id)},
        )
        ultimo = row.scalar_one_or_none()
        assert ultimo is not None

    async def test_marcar_leido_no_participante_403(
        self, async_client: AsyncClient, inbox_db: dict
    ) -> None:
        d = inbox_db
        r_hilo = await async_client.post(
            "/api/v1/inbox",
            json={"asunto": "Cerrado", "destinatario_ids": [], "mensaje": "Solo a1"},
            headers=_auth(d["user_a1"], d["tid_a"]),
        )
        hilo_id = r_hilo.json()["id"]

        r = await async_client.post(
            f"/api/v1/inbox/{hilo_id}/leer",
            headers=_auth(d["user_a2"], d["tid_a"]),   # a2 no participa
        )
        assert r.status_code == 403
