"""SlotRepository — C-13 slot_encuentro (E9).

Todas las queries filtran por tenant_id. El scoping "propio" (PROFESOR)
se delega al caller: el service pasa asignacion_ids del usuario.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.slot_encuentro import SlotEncuentro


class SlotRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_all(self, materia_id: UUID | None = None) -> list[SlotEncuentro]:
        stmt = select(SlotEncuentro).where(
            SlotEncuentro.tenant_id == self._tenant_id,
            SlotEncuentro.deleted_at.is_(None),
        )
        if materia_id is not None:
            stmt = stmt.where(SlotEncuentro.materia_id == materia_id)
        stmt = stmt.order_by(SlotEncuentro.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_asignaciones(
        self, asignacion_ids: list[UUID], materia_id: UUID | None = None
    ) -> list[SlotEncuentro]:
        if not asignacion_ids:
            return []
        stmt = select(SlotEncuentro).where(
            SlotEncuentro.tenant_id == self._tenant_id,
            SlotEncuentro.deleted_at.is_(None),
            SlotEncuentro.asignacion_id.in_(asignacion_ids),
        )
        if materia_id is not None:
            stmt = stmt.where(SlotEncuentro.materia_id == materia_id)
        stmt = stmt.order_by(SlotEncuentro.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, slot_id: UUID) -> SlotEncuentro | None:
        stmt = select(SlotEncuentro).where(
            SlotEncuentro.id == slot_id,
            SlotEncuentro.tenant_id == self._tenant_id,
            SlotEncuentro.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> SlotEncuentro:
        slot = SlotEncuentro(tenant_id=self._tenant_id, **data)
        self._session.add(slot)
        await self._session.flush()
        await self._session.refresh(slot)
        return slot

    async def soft_delete(self, slot_id: UUID) -> bool:
        slot = await self.get_by_id(slot_id)
        if slot is None:
            return False
        slot.deleted_at = datetime.utcnow()  # noqa: DTZ003 — column is TIMESTAMP WITHOUT TZ
        await self._session.flush()
        return True
