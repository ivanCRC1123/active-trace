"""InstanciaRepository — C-13 instancia_encuentro (E10).

Estado de cada instancia es independiente del slot (RN-14).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instancia_encuentro import InstanciaEncuentro


class InstanciaRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def list_all(
        self,
        materia_id: UUID | None = None,
        slot_id: UUID | None = None,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[InstanciaEncuentro]:
        stmt = select(InstanciaEncuentro).where(
            InstanciaEncuentro.tenant_id == self._tenant_id,
            InstanciaEncuentro.deleted_at.is_(None),
        )
        if materia_id:
            stmt = stmt.where(InstanciaEncuentro.materia_id == materia_id)
        if slot_id:
            stmt = stmt.where(InstanciaEncuentro.slot_id == slot_id)
        if estado:
            stmt = stmt.where(InstanciaEncuentro.estado == estado)
        if fecha_desde:
            stmt = stmt.where(InstanciaEncuentro.fecha >= fecha_desde)
        if fecha_hasta:
            stmt = stmt.where(InstanciaEncuentro.fecha <= fecha_hasta)
        stmt = stmt.order_by(InstanciaEncuentro.fecha.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_asignaciones(
        self,
        asignacion_ids: list[UUID],
        materia_id: UUID | None = None,
        slot_id: UUID | None = None,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[InstanciaEncuentro]:
        if not asignacion_ids:
            return []
        stmt = select(InstanciaEncuentro).where(
            InstanciaEncuentro.tenant_id == self._tenant_id,
            InstanciaEncuentro.deleted_at.is_(None),
            InstanciaEncuentro.asignacion_id.in_(asignacion_ids),
        )
        if materia_id:
            stmt = stmt.where(InstanciaEncuentro.materia_id == materia_id)
        if slot_id:
            stmt = stmt.where(InstanciaEncuentro.slot_id == slot_id)
        if estado:
            stmt = stmt.where(InstanciaEncuentro.estado == estado)
        if fecha_desde:
            stmt = stmt.where(InstanciaEncuentro.fecha >= fecha_desde)
        if fecha_hasta:
            stmt = stmt.where(InstanciaEncuentro.fecha <= fecha_hasta)
        stmt = stmt.order_by(InstanciaEncuentro.fecha.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_slot(self, slot_id: UUID) -> list[InstanciaEncuentro]:
        stmt = select(InstanciaEncuentro).where(
            InstanciaEncuentro.slot_id == slot_id,
            InstanciaEncuentro.tenant_id == self._tenant_id,
            InstanciaEncuentro.deleted_at.is_(None),
        ).order_by(InstanciaEncuentro.fecha.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, instancia_id: UUID) -> InstanciaEncuentro | None:
        stmt = select(InstanciaEncuentro).where(
            InstanciaEncuentro.id == instancia_id,
            InstanciaEncuentro.tenant_id == self._tenant_id,
            InstanciaEncuentro.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_bulk(self, instancias: list[InstanciaEncuentro]) -> list[InstanciaEncuentro]:
        for inst in instancias:
            self._session.add(inst)
        await self._session.flush()
        for inst in instancias:
            await self._session.refresh(inst)
        return instancias

    async def update(self, instancia_id: UUID, data: dict) -> InstanciaEncuentro | None:
        inst = await self.get_by_id(instancia_id)
        if inst is None:
            return None
        for field, value in data.items():
            setattr(inst, field, value)
        inst.updated_at = datetime.utcnow()  # noqa: DTZ003 — column is TIMESTAMP WITHOUT TZ
        await self._session.flush()
        await self._session.refresh(inst)
        return inst

    async def cancel_by_slot(self, slot_id: UUID) -> int:
        """Cancela instancias en estado Programado de un slot dado. Retorna cuántas."""
        instancias = await self.list_by_slot(slot_id)
        count = 0
        now = datetime.utcnow()  # noqa: DTZ003 — column is TIMESTAMP WITHOUT TZ
        for inst in instancias:
            if inst.estado == "Programado":
                inst.estado = "Cancelado"
                inst.updated_at = now
                count += 1
        if count:
            await self._session.flush()
        return count
