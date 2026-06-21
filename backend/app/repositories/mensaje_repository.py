"""MensajeRepository — CRUD de MensajeInterno dentro de un hilo (C-20 F11.2)."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mensaje_interno import MensajeInterno


class MensajeRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_for_hilo(self, hilo_id: UUID) -> list[MensajeInterno]:
        """Mensajes activos de un hilo, ordenados cronológicamente."""
        stmt = (
            select(MensajeInterno)
            .where(
                MensajeInterno.hilo_id == hilo_id,
                MensajeInterno.tenant_id == self._tenant_id,
                MensajeInterno.deleted_at.is_(None),
            )
            .order_by(MensajeInterno.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        hilo_id: UUID,
        cuerpo: str,
        remitente_id: Optional[UUID] = None,
    ) -> MensajeInterno:
        """Crea un mensaje. remitente_id=None indica mensaje del sistema."""
        msg = MensajeInterno(
            tenant_id=self._tenant_id,
            hilo_id=hilo_id,
            remitente_id=remitente_id,
            cuerpo=cuerpo,
        )
        self._session.add(msg)
        await self._session.flush()
        await self._session.refresh(msg)
        return msg
