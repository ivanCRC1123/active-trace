"""MateriaRepository — tenant-scoped CRUD for Materia (E3)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.materia import Materia
from app.repositories.base import BaseRepository


class MateriaRepository(BaseRepository[Materia]):
    @property
    def model_class(self) -> type[Materia]:
        return Materia

    async def get_by_codigo(self, codigo: str) -> Materia | None:
        stmt = select(Materia).where(
            Materia.tenant_id == self._tenant_id,
            Materia.codigo == codigo,
            Materia.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_id(self, id: UUID) -> Materia | None:
        stmt = select(Materia).where(
            Materia.id == id,
            Materia.tenant_id == self._tenant_id,
            Materia.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
