"""FechaAcademicaRepository — tenant-scoped CRUD for FechaAcademica (E15)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import TipoEvaluacion
from app.models.fecha_academica import FechaAcademica
from app.repositories.base import BaseRepository

_TIPO_ORDER = {
    TipoEvaluacion.Parcial: 0,
    TipoEvaluacion.TP: 1,
    TipoEvaluacion.Coloquio: 2,
    TipoEvaluacion.Recuperatorio: 3,
}


class FechaAcademicaRepository(BaseRepository[FechaAcademica]):
    @property
    def model_class(self) -> type[FechaAcademica]:
        return FechaAcademica

    async def get_by_instancia(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        tipo: TipoEvaluacion,
        numero: int,
        periodo: str,
    ) -> FechaAcademica | None:
        stmt = select(FechaAcademica).where(
            FechaAcademica.tenant_id == self._tenant_id,
            FechaAcademica.materia_id == materia_id,
            FechaAcademica.cohorte_id == cohorte_id,
            FechaAcademica.tipo == tipo,
            FechaAcademica.numero == numero,
            FechaAcademica.periodo == periodo,
            FechaAcademica.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_materia_cohorte(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        periodo: str | None = None,
    ) -> list[FechaAcademica]:
        stmt = select(FechaAcademica).where(
            FechaAcademica.tenant_id == self._tenant_id,
            FechaAcademica.materia_id == materia_id,
            FechaAcademica.cohorte_id == cohorte_id,
            FechaAcademica.deleted_at.is_(None),
        )
        if periodo is not None:
            stmt = stmt.where(FechaAcademica.periodo == periodo)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return sorted(rows, key=lambda f: (_TIPO_ORDER.get(f.tipo, 99), f.numero))

    async def list_by_cohorte(
        self,
        cohorte_id: UUID,
        periodo: str | None = None,
    ) -> list[FechaAcademica]:
        stmt = select(FechaAcademica).where(
            FechaAcademica.tenant_id == self._tenant_id,
            FechaAcademica.cohorte_id == cohorte_id,
            FechaAcademica.deleted_at.is_(None),
        )
        if periodo is not None:
            stmt = stmt.where(FechaAcademica.periodo == periodo)
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return sorted(rows, key=lambda f: (_TIPO_ORDER.get(f.tipo, 99), f.numero))
