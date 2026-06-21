"""FacturaRepository — tenant-scoped CRUD for Factura (C-18, E20)."""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import FacturaEstado
from app.models.factura import Factura
from app.repositories.base import BaseRepository


class FacturaRepository(BaseRepository[Factura]):
    @property
    def model_class(self) -> type[Factura]:
        return Factura

    async def count_abonadas_por_periodo(self, periodo: str) -> int:
        stmt = select(func.count()).where(
            Factura.tenant_id == self._tenant_id,
            Factura.periodo == periodo,
            Factura.estado == FacturaEstado.Abonada,
            Factura.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_with_filters(
        self,
        *,
        usuario_id: UUID | None = None,
        estado: FacturaEstado | None = None,
        periodo: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
        q: str | None = None,
    ) -> list[Factura]:
        stmt = select(Factura).where(
            Factura.tenant_id == self._tenant_id,
            Factura.deleted_at.is_(None),
        )
        if usuario_id is not None:
            stmt = stmt.where(Factura.usuario_id == usuario_id)
        if estado is not None:
            stmt = stmt.where(Factura.estado == estado)
        if periodo is not None:
            stmt = stmt.where(Factura.periodo == periodo)
        if fecha_desde is not None:
            stmt = stmt.where(func.date(Factura.cargada_at) >= fecha_desde)
        if fecha_hasta is not None:
            stmt = stmt.where(func.date(Factura.cargada_at) <= fecha_hasta)
        if q is not None and q.strip():
            stmt = stmt.where(Factura.detalle.ilike(f"%{q.strip()}%"))
        stmt = stmt.order_by(Factura.cargada_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
