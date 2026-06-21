"""MateriaGrupoRepository — tenant-scoped CRUD for MateriaGrupo (C-18, OD-1)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.materia_grupo import MateriaGrupo
from app.repositories.base import BaseRepository


class MateriaGrupoRepository(BaseRepository[MateriaGrupo]):
    @property
    def model_class(self) -> type[MateriaGrupo]:
        return MateriaGrupo

    async def get_by_materia_y_grupo(
        self, materia_id: UUID, grupo: str
    ) -> MateriaGrupo | None:
        stmt = select(MateriaGrupo).where(
            MateriaGrupo.tenant_id == self._tenant_id,
            MateriaGrupo.materia_id == materia_id,
            MateriaGrupo.grupo == grupo,
            MateriaGrupo.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_materia(self, materia_id: UUID) -> list[MateriaGrupo]:
        stmt = select(MateriaGrupo).where(
            MateriaGrupo.tenant_id == self._tenant_id,
            MateriaGrupo.materia_id == materia_id,
            MateriaGrupo.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_grupo(self, grupo: str) -> list[MateriaGrupo]:
        stmt = select(MateriaGrupo).where(
            MateriaGrupo.tenant_id == self._tenant_id,
            MateriaGrupo.grupo == grupo,
            MateriaGrupo.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
