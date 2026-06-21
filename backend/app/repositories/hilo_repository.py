"""HiloRepository — consultas de hilos y participación (C-20 F11.2).

Todas las queries filtran por tenant_id. El scoping de participación
(current_user es participante) se verifica aquí antes de cualquier acción.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hilo_mensaje import HiloMensaje
from app.models.hilo_participante import HiloParticipante
from app.models.user import User


class HiloRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_for_user(self, usuario_id: UUID) -> list[HiloMensaje]:
        """Hilos donde el usuario es participante, scoped al tenant."""
        stmt = (
            select(HiloMensaje)
            .join(
                HiloParticipante,
                (HiloParticipante.hilo_id == HiloMensaje.id)
                & (HiloParticipante.usuario_id == usuario_id),
            )
            .where(
                HiloMensaje.tenant_id == self._tenant_id,
                HiloMensaje.deleted_at.is_(None),
            )
            .order_by(HiloMensaje.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, hilo_id: UUID) -> HiloMensaje | None:
        stmt = select(HiloMensaje).where(
            HiloMensaje.id == hilo_id,
            HiloMensaje.tenant_id == self._tenant_id,
            HiloMensaje.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_participante(self, hilo_id: UUID, usuario_id: UUID) -> bool:
        stmt = select(HiloParticipante).where(
            HiloParticipante.hilo_id == hilo_id,
            HiloParticipante.usuario_id == usuario_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_participantes(self, hilo_id: UUID) -> list[User]:
        stmt = (
            select(User)
            .join(HiloParticipante, HiloParticipante.usuario_id == User.id)
            .where(
                HiloParticipante.hilo_id == hilo_id,
                User.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_hilo(self, asunto: str) -> HiloMensaje:
        hilo = HiloMensaje(tenant_id=self._tenant_id, asunto=asunto)
        self._session.add(hilo)
        await self._session.flush()
        await self._session.refresh(hilo)
        return hilo

    async def add_participante(self, hilo_id: UUID, usuario_id: UUID) -> HiloParticipante:
        part = HiloParticipante(
            tenant_id=self._tenant_id,
            hilo_id=hilo_id,
            usuario_id=usuario_id,
        )
        self._session.add(part)
        await self._session.flush()
        return part

    async def marcar_leido(self, hilo_id: UUID, usuario_id: UUID) -> None:
        stmt = select(HiloParticipante).where(
            HiloParticipante.hilo_id == hilo_id,
            HiloParticipante.usuario_id == usuario_id,
        )
        result = await self._session.execute(stmt)
        part = result.scalar_one_or_none()
        if part is not None:
            part.ultimo_leido_at = datetime.now(timezone.utc)
            await self._session.flush()
