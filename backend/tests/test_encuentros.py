"""C-13 encuentros-y-guardias (Sección 1) — tests de integración (F6.1–F6.5).

Cubre por propiedad:
- Slot recurrente: N instancias con fechas correctas (fecha_inicio + i*7 días)
- D-C13-1: fecha_inicio que no cae en dia_semana → 422
- Slot único: 1 instancia en fecha_unica exacta
- Scoping "propio" (PROFESOR): solo ve/edita sus propios slots e instancias
- Scoping "all" (TUTOR/COORDINADOR/ADMIN): ve todo el tenant
- Editar instancia: estado, video_url, comentario; PROFESOR ajeno → 403
- D-C13-2: reprogramar = cancelar + nueva instancia (no estado Reprogramado)
- Fragmento LMS: incluye Programado y Realizado, excluye Cancelado
- Tenant isolation: slots de otro tenant son invisibles
- Sin auth: 401 en todos los endpoints
"""

from __future__ import annotations

from datetime import date, time, timedelta
from uuid import UUID

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
from app.models.instancia_encuentro import InstanciaEncuentro
from app.models.materia import Materia
from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.slot_encuentro import SlotEncuentro
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_rol import UserRol

TENANT_A = "enc-test-a"
TENANT_B = "enc-test-b"
USER_PASS = "Test123!"

# Lunes 2026-09-07
LUNES = date(2026, 9, 7)
MARTES = date(2026, 9, 8)


async def _delete_enc_tenant_data(session: AsyncSession, *codes: str) -> None:
    """Remove enc test data scoped to specific tenant codes only."""
    for code in codes:
        tid_sub = "(SELECT id FROM tenant WHERE codigo = :c)"
        for table in ("instancia_encuentro", "slot_encuentro", "guardia"):
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id IN {tid_sub}"),
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
async def enc_db(db_session: AsyncSession) -> dict:
    """
    Tenant A: profesor_a (PROFESOR/own), profesor_b (PROFESOR/own), tutor_a (TUTOR/all),
              coord_a (COORDINADOR/all), admin_a (ADMIN/all).
    Cada PROFESOR tiene su propia asignacion en distinta materia.
    Tenant B: coord_b para tenant isolation.
    """
    await _delete_enc_tenant_data(db_session, TENANT_A, TENANT_B)

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
    tenant_a = Tenant(codigo=TENANT_A, nombre="Encuentros Test A")
    db_session.add(tenant_a)
    await db_session.flush()
    await db_session.refresh(tenant_a)
    tid_a = tenant_a.id

    prof_a = _user("enc.prof.a@test.edu.ar", tid_a, "Ana", "García")
    prof_b = _user("enc.prof.b@test.edu.ar", tid_a, "Bob", "López")
    tutor_a = _user("enc.tutor.a@test.edu.ar", tid_a, "Carlos", "Ruiz")
    coord_a = _user("enc.coord.a@test.edu.ar", tid_a, "Diana", "Pérez")
    admin_a = _user("enc.admin.a@test.edu.ar", tid_a, "Eva", "Morales")
    db_session.add_all([prof_a, prof_b, tutor_a, coord_a, admin_a])
    await db_session.flush()
    for u in [prof_a, prof_b, tutor_a, coord_a, admin_a]:
        await db_session.refresh(u)

    # Roles
    rol_prof = Rol(tenant_id=tid_a, nombre="PROFESOR", descripcion="Profesor")
    rol_tutor = Rol(tenant_id=tid_a, nombre="TUTOR", descripcion="Tutor")
    rol_coord = Rol(tenant_id=tid_a, nombre="COORDINADOR", descripcion="Coordinador")
    rol_admin = Rol(tenant_id=tid_a, nombre="ADMIN", descripcion="Admin")
    db_session.add_all([rol_prof, rol_tutor, rol_coord, rol_admin])
    await db_session.flush()
    for r in [rol_prof, rol_tutor, rol_coord, rol_admin]:
        await db_session.refresh(r)

    # Permisos
    p_enc = Permiso(
        tenant_id=tid_a, codigo="encuentros:gestionar", modulo="encuentros",
        descripcion="Gestionar encuentros"
    )
    db_session.add(p_enc)
    await db_session.flush()
    await db_session.refresh(p_enc)

    db_session.add_all([
        RolPermiso(tenant_id=tid_a, rol_id=rol_prof.id, permiso_id=p_enc.id, scope="own"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_tutor.id, permiso_id=p_enc.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_coord.id, permiso_id=p_enc.id, scope="all"),
        RolPermiso(tenant_id=tid_a, rol_id=rol_admin.id, permiso_id=p_enc.id, scope="all"),
        UserRol(tenant_id=tid_a, user_id=prof_a.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid_a, user_id=prof_b.id, rol_id=rol_prof.id),
        UserRol(tenant_id=tid_a, user_id=tutor_a.id, rol_id=rol_tutor.id),
        UserRol(tenant_id=tid_a, user_id=coord_a.id, rol_id=rol_coord.id),
        UserRol(tenant_id=tid_a, user_id=admin_a.id, rol_id=rol_admin.id),
    ])
    await db_session.flush()

    # Catálogo
    carrera_a = Carrera(tenant_id=tid_a, codigo="ING-ENC", nombre="Ingeniería")
    mat_a = Materia(tenant_id=tid_a, codigo="MAT_I", nombre="Análisis I")
    mat_b = Materia(tenant_id=tid_a, codigo="MAT_II", nombre="Análisis II")
    db_session.add_all([carrera_a, mat_a, mat_b])
    await db_session.flush()
    for m in [carrera_a, mat_a, mat_b]:
        await db_session.refresh(m)

    cohorte_a = Cohorte(
        tenant_id=tid_a, carrera_id=carrera_a.id, nombre="MAR-2026", anio=2026,
        vig_desde=date(2026, 3, 1),
    )
    db_session.add(cohorte_a)
    await db_session.flush()
    await db_session.refresh(cohorte_a)

    # Asignaciones: cada PROFESOR tiene la suya en diferente materia
    asig_a = Asignacion(
        tenant_id=tid_a, usuario_id=prof_a.id, rol_id=rol_prof.id,
        materia_id=mat_a.id, carrera_id=carrera_a.id, cohorte_id=cohorte_a.id,
        desde=date(2026, 3, 1),
    )
    asig_b = Asignacion(
        tenant_id=tid_a, usuario_id=prof_b.id, rol_id=rol_prof.id,
        materia_id=mat_b.id, carrera_id=carrera_a.id, cohorte_id=cohorte_a.id,
        desde=date(2026, 3, 1),
    )
    db_session.add_all([asig_a, asig_b])
    await db_session.flush()
    for a in [asig_a, asig_b]:
        await db_session.refresh(a)

    # ── Tenant B ─────────────────────────────────────────────────────────────
    tenant_b = Tenant(codigo=TENANT_B, nombre="Encuentros Test B")
    db_session.add(tenant_b)
    await db_session.flush()
    await db_session.refresh(tenant_b)
    tid_b = tenant_b.id

    coord_b = _user("enc.coord.b@test.edu.ar", tid_b, "Fede", "Soto")
    db_session.add(coord_b)
    await db_session.flush()
    await db_session.refresh(coord_b)

    rol_coord_b = Rol(tenant_id=tid_b, nombre="COORDINADOR", descripcion="Coordinador B")
    db_session.add(rol_coord_b)
    await db_session.flush()
    await db_session.refresh(rol_coord_b)

    p_enc_b = Permiso(
        tenant_id=tid_b, codigo="encuentros:gestionar", modulo="encuentros",
        descripcion="Gestionar encuentros"
    )
    db_session.add(p_enc_b)
    await db_session.flush()
    await db_session.refresh(p_enc_b)

    db_session.add_all([
        RolPermiso(tenant_id=tid_b, rol_id=rol_coord_b.id, permiso_id=p_enc_b.id, scope="all"),
        UserRol(tenant_id=tid_b, user_id=coord_b.id, rol_id=rol_coord_b.id),
    ])

    mat_b2 = Materia(tenant_id=tid_b, codigo="MAT_B", nombre="Materia B")
    carrera_b = Carrera(tenant_id=tid_b, codigo="ING-B", nombre="Ing B")
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

    def _token(user: User, tid: UUID, rol: str = "PROFESOR") -> str:
        return create_access_token(user.id, tid, [rol])

    return {
        "tid_a": tid_a, "tid_b": tid_b,
        "prof_a": prof_a, "prof_b": prof_b,
        "tutor_a": tutor_a, "coord_a": coord_a, "admin_a": admin_a,
        "coord_b": coord_b,
        "mat_a": mat_a, "mat_b": mat_b, "mat_b2": mat_b2,
        "asig_a": asig_a, "asig_b": asig_b, "asig_coord_b": asig_coord_b,
        "token_prof_a": _token(prof_a, tid_a, "PROFESOR"),
        "token_prof_b": _token(prof_b, tid_a, "PROFESOR"),
        "token_tutor_a": _token(tutor_a, tid_a, "TUTOR"),
        "token_coord_a": _token(coord_a, tid_a, "COORDINADOR"),
        "token_admin_a": _token(admin_a, tid_a, "ADMIN"),
        "token_coord_b": _token(coord_b, tid_b, "COORDINADOR"),
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _slot_recurrente(asig_id: UUID, mat_id: UUID) -> dict:
    return {
        "asignacion_id": str(asig_id),
        "materia_id": str(mat_id),
        "titulo": "Clase semanal",
        "hora": "18:00:00",
        "modo": "recurrente",
        "dia_semana": "Lunes",
        "fecha_inicio": str(LUNES),
        "cant_semanas": 4,
    }


def _slot_unico(asig_id: UUID, mat_id: UUID, fecha: date) -> dict:
    return {
        "asignacion_id": str(asig_id),
        "materia_id": str(mat_id),
        "titulo": "Recuperatorio",
        "hora": "10:00:00",
        "modo": "unico",
        "fecha_unica": str(fecha),
    }


# ── TestSlotCrearRecurrente ───────────────────────────────────────────────────


class TestSlotCrearRecurrente:
    async def test_crea_4_instancias_en_fechas_correctas(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["modo"] == "recurrente"
        instancias = body["instancias"]
        assert len(instancias) == 4
        for i, inst in enumerate(instancias):
            expected = (LUNES + timedelta(weeks=i)).isoformat()
            assert inst["fecha"] == expected
            assert inst["estado"] == "Programado"
            assert inst["asignacion_id"] == str(enc_db["asig_a"].id)

    async def test_instancia_0_es_fecha_inicio(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 201
        assert r.json()["instancias"][0]["fecha"] == LUNES.isoformat()

    async def test_fecha_inicio_no_coincide_con_dia_semana_422(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        payload = _slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id)
        payload["fecha_inicio"] = str(MARTES)  # Martes != Lunes → 422
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=payload,
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 422

    async def test_profesor_crea_con_asignacion_ajena_403(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        # prof_b intenta usar asig_a (de prof_a)
        payload = _slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id)
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=payload,
            headers=_auth(enc_db["token_prof_b"]),
        )
        assert r.status_code == 403

    async def test_sin_auth_401(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
        )
        assert r.status_code == 401

    async def test_cant_semanas_0_422(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        payload = _slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id)
        payload["cant_semanas"] = 0
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=payload,
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 422


# ── TestSlotCrearUnico ────────────────────────────────────────────────────────


class TestSlotCrearUnico:
    async def test_crea_1_instancia_en_fecha_unica(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        fecha = date(2026, 10, 5)
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_unico(enc_db["asig_a"].id, enc_db["mat_a"].id, fecha),
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["modo"] == "unico"
        instancias = body["instancias"]
        assert len(instancias) == 1
        assert instancias[0]["fecha"] == fecha.isoformat()
        assert instancias[0]["estado"] == "Programado"

    async def test_unico_con_cant_semanas_422(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        payload = _slot_unico(enc_db["asig_a"].id, enc_db["mat_a"].id, date(2026, 10, 5))
        payload["cant_semanas"] = 3   # inválido en modo único
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=payload,
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 422

    async def test_tutor_crea_slot_unico_de_cualquier_asignacion(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        # TUTOR tiene scope=all, puede usar asig_a aunque no sea suya
        payload = _slot_unico(enc_db["asig_a"].id, enc_db["mat_a"].id, date(2026, 10, 12))
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=payload,
            headers=_auth(enc_db["token_tutor_a"]),
        )
        assert r.status_code == 201


# ── TestScopingListar ─────────────────────────────────────────────────────────


class TestScopingListar:
    async def test_profesor_solo_ve_sus_slots(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        # prof_a crea slot propio, prof_b crea slot propio
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_b"].id, enc_db["mat_b"].id),
            headers=_auth(enc_db["token_prof_b"]),
        )
        r = await async_client.get(
            "/api/v1/encuentros/slots", headers=_auth(enc_db["token_prof_a"])
        )
        assert r.status_code == 200
        slots = r.json()
        # Prof_a solo ve los suyos
        asig_ids = {s["asignacion_id"] for s in slots}
        assert asig_ids == {str(enc_db["asig_a"].id)}

    async def test_coordinador_ve_todos_los_slots(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_b"].id, enc_db["mat_b"].id),
            headers=_auth(enc_db["token_prof_b"]),
        )
        r = await async_client.get(
            "/api/v1/encuentros/slots", headers=_auth(enc_db["token_coord_a"])
        )
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_profesor_solo_ve_sus_instancias(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_b"].id, enc_db["mat_b"].id),
            headers=_auth(enc_db["token_prof_b"]),
        )
        r = await async_client.get(
            "/api/v1/encuentros/instancias", headers=_auth(enc_db["token_prof_a"])
        )
        assert r.status_code == 200
        insts = r.json()
        # Solo las 4 instancias de prof_a
        asig_ids = {i["asignacion_id"] for i in insts}
        assert asig_ids == {str(enc_db["asig_a"].id)}
        assert len(insts) == 4


# ── TestEditarInstancia ───────────────────────────────────────────────────────


class TestEditarInstancia:
    async def _crear_slot_y_get_instancia(
        self, client: AsyncClient, enc_db: dict, token: str, asig_id: UUID, mat_id: UUID
    ) -> dict:
        r = await client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(asig_id, mat_id),
            headers=_auth(token),
        )
        assert r.status_code == 201
        return r.json()["instancias"][0]

    async def test_profesor_edita_instancia_propia_200(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        inst = await self._crear_slot_y_get_instancia(
            async_client, enc_db, enc_db["token_prof_a"],
            enc_db["asig_a"].id, enc_db["mat_a"].id,
        )
        r = await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst['id']}",
            json={"estado": "Realizado", "comentario": "OK"},
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 200
        body = r.json()
        assert body["estado"] == "Realizado"
        assert body["comentario"] == "OK"

    async def test_profesor_edita_instancia_ajena_403(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        # prof_a crea su slot
        inst_a = await self._crear_slot_y_get_instancia(
            async_client, enc_db, enc_db["token_prof_a"],
            enc_db["asig_a"].id, enc_db["mat_a"].id,
        )
        # prof_b intenta editar la instancia de prof_a → 403
        r = await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst_a['id']}",
            json={"estado": "Cancelado"},
            headers=_auth(enc_db["token_prof_b"]),
        )
        assert r.status_code == 403

    async def test_tutor_edita_instancia_ajena_200(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        inst_a = await self._crear_slot_y_get_instancia(
            async_client, enc_db, enc_db["token_prof_a"],
            enc_db["asig_a"].id, enc_db["mat_a"].id,
        )
        # TUTOR (scope=all) puede editar cualquier instancia
        r = await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst_a['id']}",
            json={"estado": "Realizado"},
            headers=_auth(enc_db["token_tutor_a"]),
        )
        assert r.status_code == 200
        assert r.json()["estado"] == "Realizado"

    async def test_editar_video_url_no_requiere_estado_realizado(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        # D-C13-5: backend permisivo — video_url editable sin restricción de estado
        inst = await self._crear_slot_y_get_instancia(
            async_client, enc_db, enc_db["token_prof_a"],
            enc_db["asig_a"].id, enc_db["mat_a"].id,
        )
        r = await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst['id']}",
            json={"video_url": "https://video.example.com/rec"},
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 200
        assert r.json()["video_url"] == "https://video.example.com/rec"
        assert r.json()["estado"] == "Programado"  # no cambió

    async def test_reprogramar_es_cancelar_mas_nueva_instancia(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        """D-C13-2: reprogramar = cancelar la instancia vieja + crear una nueva."""
        inst = await self._crear_slot_y_get_instancia(
            async_client, enc_db, enc_db["token_prof_a"],
            enc_db["asig_a"].id, enc_db["mat_a"].id,
        )
        # Paso 1: cancelar la instancia vieja
        r_cancel = await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst['id']}",
            json={"estado": "Cancelado", "comentario": "Reprogramada"},
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r_cancel.status_code == 200
        assert r_cancel.json()["estado"] == "Cancelado"

        # Paso 2: crear slot único en nueva fecha (la "nueva instancia")
        nueva_fecha = date(2026, 9, 21)
        r_nuevo = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_unico(enc_db["asig_a"].id, enc_db["mat_a"].id, nueva_fecha),
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r_nuevo.status_code == 201
        nueva_inst = r_nuevo.json()["instancias"][0]
        assert nueva_inst["fecha"] == nueva_fecha.isoformat()
        assert nueva_inst["estado"] == "Programado"


# ── TestEliminarSlot ──────────────────────────────────────────────────────────


class TestEliminarSlot:
    async def test_eliminar_slot_cancela_programadas(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        slot_id = r.json()["id"]
        # Primero marcamos una instancia como Realizado (no debe cancelarse)
        inst_id = r.json()["instancias"][0]["id"]
        await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst_id}",
            json={"estado": "Realizado"},
            headers=_auth(enc_db["token_prof_a"]),
        )
        # Eliminar slot
        r_del = await async_client.delete(
            f"/api/v1/encuentros/slots/{slot_id}",
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r_del.status_code == 204
        # El slot no aparece más
        r_get = await async_client.get(
            "/api/v1/encuentros/slots", headers=_auth(enc_db["token_prof_a"])
        )
        assert not any(s["id"] == slot_id for s in r_get.json())

    async def test_profesor_no_puede_eliminar_slot_ajeno(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        r = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        slot_id = r.json()["id"]
        r_del = await async_client.delete(
            f"/api/v1/encuentros/slots/{slot_id}",
            headers=_auth(enc_db["token_prof_b"]),
        )
        assert r_del.status_code == 403


# ── TestFragmentoLMS ──────────────────────────────────────────────────────────


class TestFragmentoLMS:
    async def test_incluye_programados_con_meet_url(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        payload = _slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id)
        payload["meet_url"] = "https://meet.example.com/abc"
        await async_client.post(
            "/api/v1/encuentros/slots", json=payload, headers=_auth(enc_db["token_prof_a"])
        )
        r = await async_client.get(
            "/api/v1/encuentros/fragmento-lms",
            params={"materia_id": str(enc_db["mat_a"].id)},
            headers=_auth(enc_db["token_prof_a"]),
        )
        assert r.status_code == 200
        frag = r.json()["fragmento"]
        assert "Programados" in frag
        assert "Sala virtual" in frag
        assert "meet.example.com" in frag

    async def test_incluye_realizados_con_video_url(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        r_slot = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        inst_id = r_slot.json()["instancias"][0]["id"]
        await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst_id}",
            json={"estado": "Realizado", "video_url": "https://drive.example.com/video"},
            headers=_auth(enc_db["token_prof_a"]),
        )
        r = await async_client.get(
            "/api/v1/encuentros/fragmento-lms",
            params={"materia_id": str(enc_db["mat_a"].id)},
            headers=_auth(enc_db["token_prof_a"]),
        )
        frag = r.json()["fragmento"]
        assert "Realizados" in frag
        assert "Grabación" in frag

    async def test_excluye_cancelados(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        r_slot = await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_unico(enc_db["asig_a"].id, enc_db["mat_a"].id, date(2026, 10, 5)),
            headers=_auth(enc_db["token_prof_a"]),
        )
        inst_id = r_slot.json()["instancias"][0]["id"]
        await async_client.patch(
            f"/api/v1/encuentros/instancias/{inst_id}",
            json={"estado": "Cancelado"},
            headers=_auth(enc_db["token_prof_a"]),
        )
        r = await async_client.get(
            "/api/v1/encuentros/fragmento-lms",
            params={"materia_id": str(enc_db["mat_a"].id)},
            headers=_auth(enc_db["token_prof_a"]),
        )
        frag = r.json()["fragmento"]
        assert "Programados" not in frag
        assert "Realizados" not in frag
        assert "Cancelado" not in frag


# ── TestTenantIsolation ───────────────────────────────────────────────────────


class TestTenantIsolation:
    async def test_slot_de_tenant_a_invisible_para_tenant_b(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        r = await async_client.get(
            "/api/v1/encuentros/slots", headers=_auth(enc_db["token_coord_b"])
        )
        assert r.status_code == 200
        assert r.json() == []

    async def test_instancias_de_tenant_a_invisibles_para_tenant_b(
        self, async_client: AsyncClient, enc_db: dict
    ) -> None:
        await async_client.post(
            "/api/v1/encuentros/slots",
            json=_slot_recurrente(enc_db["asig_a"].id, enc_db["mat_a"].id),
            headers=_auth(enc_db["token_prof_a"]),
        )
        r = await async_client.get(
            "/api/v1/encuentros/instancias", headers=_auth(enc_db["token_coord_b"])
        )
        assert r.status_code == 200
        assert r.json() == []
