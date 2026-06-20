"""AsignacionRepository — tenant-scoped queries for Asignacion with vigencia filters."""

from datetime import date
from typing import Sequence

from sqlalchemy import select, or_

from app.models.asignacion import Asignacion
from app.repositories.base import BaseRepository


class AsignacionRepository(BaseRepository[Asignacion]):

    @property
    def model_class(self) -> type[Asignacion]:
        return Asignacion

    async def list_vigentes(self, today: date) -> Sequence[Asignacion]:
        stmt = select(Asignacion).where(
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.deleted_at.is_(None),
            Asignacion.desde <= today,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= today),
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_vencidas(self, today: date) -> Sequence[Asignacion]:
        stmt = select(Asignacion).where(
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.deleted_at.is_(None),
            or_(Asignacion.desde > today, Asignacion.hasta < today),
        )
        return (await self._session.execute(stmt)).scalars().all()
