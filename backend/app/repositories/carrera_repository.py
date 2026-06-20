"""CarreraRepository — tenant-scoped CRUD for Carrera (E1)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.carrera import Carrera
from app.repositories.base import BaseRepository


class CarreraRepository(BaseRepository[Carrera]):
    @property
    def model_class(self) -> type[Carrera]:
        return Carrera

    async def get_by_codigo(self, codigo: str) -> Carrera | None:
        stmt = select(Carrera).where(
            Carrera.tenant_id == self._tenant_id,
            Carrera.codigo == codigo,
            Carrera.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_id(self, id: UUID) -> Carrera | None:
        stmt = select(Carrera).where(
            Carrera.id == id,
            Carrera.tenant_id == self._tenant_id,
            Carrera.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
