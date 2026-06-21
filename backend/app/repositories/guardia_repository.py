"""GuardiaRepository — C-13 guardias (F6.6, E11)."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guardia import Guardia


class GuardiaRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def _base(self):
        return select(Guardia).where(
            Guardia.tenant_id == self._tenant_id,
            Guardia.deleted_at.is_(None),
        )

    async def list_all(
        self,
        materia_id: UUID | None = None,
        carrera_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
        asignacion_id: UUID | None = None,
    ) -> list[Guardia]:
        stmt = self._base()
        if materia_id:
            stmt = stmt.where(Guardia.materia_id == materia_id)
        if carrera_id:
            stmt = stmt.where(Guardia.carrera_id == carrera_id)
        if cohorte_id:
            stmt = stmt.where(Guardia.cohorte_id == cohorte_id)
        if estado:
            stmt = stmt.where(Guardia.estado == estado)
        if fecha_desde:
            stmt = stmt.where(Guardia.fecha >= fecha_desde)
        if fecha_hasta:
            stmt = stmt.where(Guardia.fecha <= fecha_hasta)
        if asignacion_id:
            stmt = stmt.where(Guardia.asignacion_id == asignacion_id)
        stmt = stmt.order_by(Guardia.fecha.asc().nullsfirst(), Guardia.created_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_asignaciones(
        self,
        asignacion_ids: list[UUID],
        materia_id: UUID | None = None,
        carrera_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> list[Guardia]:
        if not asignacion_ids:
            return []
        stmt = self._base().where(Guardia.asignacion_id.in_(asignacion_ids))
        if materia_id:
            stmt = stmt.where(Guardia.materia_id == materia_id)
        if carrera_id:
            stmt = stmt.where(Guardia.carrera_id == carrera_id)
        if cohorte_id:
            stmt = stmt.where(Guardia.cohorte_id == cohorte_id)
        if estado:
            stmt = stmt.where(Guardia.estado == estado)
        if fecha_desde:
            stmt = stmt.where(Guardia.fecha >= fecha_desde)
        if fecha_hasta:
            stmt = stmt.where(Guardia.fecha <= fecha_hasta)
        stmt = stmt.order_by(Guardia.fecha.asc().nullsfirst(), Guardia.created_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, guardia_id: UUID) -> Guardia | None:
        stmt = self._base().where(Guardia.id == guardia_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> Guardia:
        guardia = Guardia(**data, tenant_id=self._tenant_id)
        self._session.add(guardia)
        await self._session.flush()
        await self._session.refresh(guardia)
        return guardia

    async def update(self, guardia_id: UUID, data: dict) -> Guardia | None:
        guardia = await self.get_by_id(guardia_id)
        if guardia is None:
            return None
        for field, value in data.items():
            setattr(guardia, field, value)
        await self._session.flush()
        await self._session.refresh(guardia)
        return guardia
