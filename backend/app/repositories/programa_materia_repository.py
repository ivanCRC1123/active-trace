"""ProgramaMateriaRepository — tenant-scoped CRUD for ProgramaMateria (E16)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.programa_materia import ProgramaMateria
from app.repositories.base import BaseRepository


class ProgramaMateriaRepository(BaseRepository[ProgramaMateria]):
    @property
    def model_class(self) -> type[ProgramaMateria]:
        return ProgramaMateria

    async def get_by_combinacion(
        self, materia_id: UUID, carrera_id: UUID, cohorte_id: UUID
    ) -> ProgramaMateria | None:
        stmt = select(ProgramaMateria).where(
            ProgramaMateria.tenant_id == self._tenant_id,
            ProgramaMateria.materia_id == materia_id,
            ProgramaMateria.carrera_id == carrera_id,
            ProgramaMateria.cohorte_id == cohorte_id,
            ProgramaMateria.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_materia(self, materia_id: UUID) -> list[ProgramaMateria]:
        stmt = select(ProgramaMateria).where(
            ProgramaMateria.tenant_id == self._tenant_id,
            ProgramaMateria.materia_id == materia_id,
            ProgramaMateria.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_cohorte(self, cohorte_id: UUID) -> list[ProgramaMateria]:
        stmt = select(ProgramaMateria).where(
            ProgramaMateria.tenant_id == self._tenant_id,
            ProgramaMateria.cohorte_id == cohorte_id,
            ProgramaMateria.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
