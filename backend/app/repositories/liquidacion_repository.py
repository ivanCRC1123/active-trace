"""LiquidacionRepository — tenant-scoped queries for Liquidacion (C-18, E19)."""

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import LiquidacionEstado, RolLiquidable
from app.models.liquidacion import Liquidacion
from app.repositories.base import BaseRepository


class LiquidacionRepository(BaseRepository[Liquidacion]):
    @property
    def model_class(self) -> type[Liquidacion]:
        return Liquidacion

    async def get_by_docente_periodo(
        self, cohorte_id: UUID, usuario_id: UUID, rol: RolLiquidable, periodo: str
    ) -> Liquidacion | None:
        stmt = select(Liquidacion).where(
            Liquidacion.tenant_id == self._tenant_id,
            Liquidacion.cohorte_id == cohorte_id,
            Liquidacion.usuario_id == usuario_id,
            Liquidacion.rol == rol,
            Liquidacion.periodo == periodo,
            Liquidacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_cohorte_periodo(
        self, cohorte_id: UUID, periodo: str
    ) -> list[Liquidacion]:
        stmt = select(Liquidacion).where(
            Liquidacion.tenant_id == self._tenant_id,
            Liquidacion.cohorte_id == cohorte_id,
            Liquidacion.periodo == periodo,
            Liquidacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def tiene_cerradas(self, cohorte_id: UUID, periodo: str) -> bool:
        """Return True if any Cerrada liquidacion exists for (cohorte, periodo)."""
        stmt = select(sa.literal(1)).where(
            Liquidacion.tenant_id == self._tenant_id,
            Liquidacion.cohorte_id == cohorte_id,
            Liquidacion.periodo == periodo,
            Liquidacion.estado == LiquidacionEstado.Cerrada,
            Liquidacion.deleted_at.is_(None),
        ).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def cerrar_batch(self, cohorte_id: UUID, periodo: str) -> int:
        """Atomically close all closeable Abierta liquidaciones for (cohorte, periodo).

        Closeable = Abierta AND NOT datos_bancarios_incompletos AND NOT excluido_por_factura.
        Returns the count of rows updated.
        """
        stmt = (
            sa.update(Liquidacion)
            .where(
                Liquidacion.tenant_id == self._tenant_id,
                Liquidacion.cohorte_id == cohorte_id,
                Liquidacion.periodo == periodo,
                Liquidacion.estado == LiquidacionEstado.Abierta,
                Liquidacion.datos_bancarios_incompletos.is_(False),
                Liquidacion.excluido_por_factura.is_(False),
                Liquidacion.deleted_at.is_(None),
            )
            .values(estado=LiquidacionEstado.Cerrada)
            .returning(Liquidacion.id)
        )
        result = await self._session.execute(stmt)
        return len(result.all())
