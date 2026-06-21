"""SalarioPlusRepository — tenant-scoped CRUD + vigencia queries for SalarioPlus (C-18, E18)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import RolLiquidable
from app.models.salario_plus import SalarioPlus
from app.repositories.base import BaseRepository


class SalarioPlusRepository(BaseRepository[SalarioPlus]):
    @property
    def model_class(self) -> type[SalarioPlus]:
        return SalarioPlus

    async def get_vigente(
        self, grupo: str, rol: RolLiquidable, periodo: date
    ) -> SalarioPlus | None:
        """Return the active SalarioPlus for (grupo, rol, date), if any."""
        stmt = select(SalarioPlus).where(
            SalarioPlus.tenant_id == self._tenant_id,
            SalarioPlus.grupo == grupo,
            SalarioPlus.rol == rol,
            SalarioPlus.desde <= periodo,
            (SalarioPlus.hasta.is_(None)) | (SalarioPlus.hasta >= periodo),
            SalarioPlus.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_grupo(self, grupo: str) -> list[SalarioPlus]:
        stmt = select(SalarioPlus).where(
            SalarioPlus.tenant_id == self._tenant_id,
            SalarioPlus.grupo == grupo,
            SalarioPlus.deleted_at.is_(None),
        ).order_by(SalarioPlus.desde.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_rol(self, rol: RolLiquidable) -> list[SalarioPlus]:
        stmt = select(SalarioPlus).where(
            SalarioPlus.tenant_id == self._tenant_id,
            SalarioPlus.rol == rol,
            SalarioPlus.deleted_at.is_(None),
        ).order_by(SalarioPlus.desde.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
