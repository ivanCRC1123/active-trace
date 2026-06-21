"""SalarioBaseRepository — tenant-scoped CRUD + vigencia queries for SalarioBase (C-18, E17)."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import RolLiquidable
from app.models.salario_base import SalarioBase
from app.repositories.base import BaseRepository


class SalarioBaseRepository(BaseRepository[SalarioBase]):
    @property
    def model_class(self) -> type[SalarioBase]:
        return SalarioBase

    async def get_vigente(self, rol: RolLiquidable, periodo: date) -> SalarioBase | None:
        """Return the active SalarioBase for (rol, date), if any.

        A record is considered active when desde <= periodo and (hasta IS NULL OR hasta >= periodo).
        """
        stmt = select(SalarioBase).where(
            SalarioBase.tenant_id == self._tenant_id,
            SalarioBase.rol == rol,
            SalarioBase.desde <= periodo,
            (SalarioBase.hasta.is_(None)) | (SalarioBase.hasta >= periodo),
            SalarioBase.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_rol(self, rol: RolLiquidable) -> list[SalarioBase]:
        stmt = select(SalarioBase).where(
            SalarioBase.tenant_id == self._tenant_id,
            SalarioBase.rol == rol,
            SalarioBase.deleted_at.is_(None),
        ).order_by(SalarioBase.desde.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
