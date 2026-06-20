"""CohorteRepository — tenant-scoped CRUD for Cohorte (E2)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cohorte import Cohorte
from app.repositories.base import BaseRepository


class CohorteRepository(BaseRepository[Cohorte]):
    @property
    def model_class(self) -> type[Cohorte]:
        return Cohorte

    async def get_active_by_id(self, id: UUID) -> Cohorte | None:
        stmt = select(Cohorte).where(
            Cohorte.id == id,
            Cohorte.tenant_id == self._tenant_id,
            Cohorte.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_nombre_carrera(self, nombre: str, carrera_id: UUID) -> Cohorte | None:
        stmt = select(Cohorte).where(
            Cohorte.tenant_id == self._tenant_id,
            Cohorte.carrera_id == carrera_id,
            Cohorte.nombre == nombre,
            Cohorte.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_carrera(self, carrera_id: UUID) -> list[Cohorte]:
        stmt = select(Cohorte).where(
            Cohorte.tenant_id == self._tenant_id,
            Cohorte.carrera_id == carrera_id,
            Cohorte.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
