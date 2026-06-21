"""InboxService — mensajería interna self-scoped (C-20 F11.2).

Reglas de acceso:
- listar_hilos: solo hilos donde current_user es participante.
- get_hilo / responder / marcar_leido: verifica participación ANTES de actuar.
  Un usuario que no participa en el hilo recibe PermissionError (→ 403).
- PII: nombre/apellidos son columnas no cifradas. email/cuil NUNCA se retornan.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hilo_mensaje import HiloMensaje
from app.models.mensaje_interno import MensajeInterno
from app.models.user import User
from app.repositories.hilo_repository import HiloRepository
from app.repositories.mensaje_repository import MensajeRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import CurrentUser
from app.schemas.inbox import (
    HiloCreate,
    HiloDetalle,
    HiloResponse,
    MensajeCreate,
    MensajeResponse,
    ParticipanteResponse,
)


def _participante_resp(user: User) -> ParticipanteResponse:
    return ParticipanteResponse(
        usuario_id=user.id,
        nombre=user.nombre,
        apellidos=user.apellidos,
    )


def _mensaje_resp(msg: MensajeInterno, users_by_id: dict[UUID, User]) -> MensajeResponse:
    remitente = users_by_id.get(msg.remitente_id) if msg.remitente_id else None
    return MensajeResponse(
        id=msg.id,
        hilo_id=msg.hilo_id,
        remitente_id=msg.remitente_id,
        remitente_nombre=remitente.nombre if remitente else None,
        remitente_apellidos=remitente.apellidos if remitente else None,
        cuerpo=msg.cuerpo,
        created_at=msg.created_at,
    )


class InboxService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _hilos(self, tenant_id: UUID) -> HiloRepository:
        return HiloRepository(self._session, tenant_id)

    def _mensajes(self, tenant_id: UUID) -> MensajeRepository:
        return MensajeRepository(self._session, tenant_id)

    def _usuarios(self, tenant_id: UUID) -> UsuarioRepository:
        return UsuarioRepository(self._session, tenant_id)

    async def _assert_participante(self, tenant_id: UUID, hilo_id: UUID, usuario_id: UUID) -> HiloMensaje:
        """Verifica que el hilo existe en el tenant Y que el usuario es participante.

        Raises:
            LookupError: hilo no existe (→ 404)
            PermissionError: hilo existe pero usuario no participa (→ 403)
        """
        hilo = await self._hilos(tenant_id).get_by_id(hilo_id)
        if hilo is None:
            raise LookupError("hilo_no_encontrado")
        es_part = await self._hilos(tenant_id).is_participante(hilo_id, usuario_id)
        if not es_part:
            raise PermissionError("no_participante")
        return hilo

    async def listar_hilos(self, current_user: CurrentUser) -> list[HiloResponse]:
        repo = self._hilos(current_user.tenant_id)
        hilos = await repo.list_for_user(current_user.user_id)
        resultado = []
        for hilo in hilos:
            participantes = await repo.get_participantes(hilo.id)
            resultado.append(
                HiloResponse(
                    id=hilo.id,
                    asunto=hilo.asunto,
                    participantes=[_participante_resp(u) for u in participantes],
                    created_at=hilo.created_at,
                )
            )
        return resultado

    async def crear_hilo(self, current_user: CurrentUser, data: HiloCreate) -> HiloDetalle:
        repo = self._hilos(current_user.tenant_id)
        msg_repo = self._mensajes(current_user.tenant_id)

        hilo = await repo.create_hilo(data.asunto)

        # Agregar al creador + destinatarios como participantes (deduplicados)
        todos_ids: list[UUID] = [current_user.user_id] + [
            uid for uid in data.destinatario_ids if uid != current_user.user_id
        ]
        for uid in todos_ids:
            await repo.add_participante(hilo.id, uid)

        # Mensaje inicial del creador
        await msg_repo.create(hilo.id, data.mensaje, remitente_id=current_user.user_id)

        await self._session.commit()
        return await self.get_hilo(current_user, hilo.id)

    async def get_hilo(self, current_user: CurrentUser, hilo_id: UUID) -> HiloDetalle:
        hilo = await self._assert_participante(
            current_user.tenant_id, hilo_id, current_user.user_id
        )
        repo = self._hilos(current_user.tenant_id)
        participantes = await repo.get_participantes(hilo_id)
        mensajes = await self._mensajes(current_user.tenant_id).list_for_hilo(hilo_id)

        users_by_id = {u.id: u for u in participantes}
        return HiloDetalle(
            id=hilo.id,
            asunto=hilo.asunto,
            participantes=[_participante_resp(u) for u in participantes],
            mensajes=[_mensaje_resp(m, users_by_id) for m in mensajes],
            created_at=hilo.created_at,
        )

    async def responder(
        self, current_user: CurrentUser, hilo_id: UUID, data: MensajeCreate
    ) -> MensajeResponse:
        await self._assert_participante(
            current_user.tenant_id, hilo_id, current_user.user_id
        )
        msg = await self._mensajes(current_user.tenant_id).create(
            hilo_id, data.cuerpo, remitente_id=current_user.user_id
        )
        await self._session.commit()
        user = await self._usuarios(current_user.tenant_id).get_by_id(current_user.user_id)
        users_by_id = {user.id: user} if user else {}
        return _mensaje_resp(msg, users_by_id)

    async def marcar_leido(self, current_user: CurrentUser, hilo_id: UUID) -> None:
        await self._assert_participante(
            current_user.tenant_id, hilo_id, current_user.user_id
        )
        await self._hilos(current_user.tenant_id).marcar_leido(hilo_id, current_user.user_id)
        await self._session.commit()
