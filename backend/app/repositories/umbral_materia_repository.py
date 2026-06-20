"""UmbralMateriaRepository — tenant-scoped queries for UmbralMateria (E8)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.umbral_materia import UmbralMateria
from app.repositories.base import BaseRepository

_DEFAULT_UMBRAL_PCT = 60
_DEFAULT_VALORES = ["Satisfactorio", "Supera lo esperado"]


class UmbralMateriaRepository(BaseRepository[UmbralMateria]):

    @property
    def model_class(self) -> type[UmbralMateria]:
        return UmbralMateria

    async def get_by_asignacion(self, asignacion_id: UUID) -> UmbralMateria | None:
        stmt = select(UmbralMateria).where(
            UmbralMateria.tenant_id == UUID(self._tenant_id),
            UmbralMateria.asignacion_id == asignacion_id,
            UmbralMateria.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        *,
        asignacion_id: UUID,
        materia_id: UUID,
        umbral_pct: int,
        valores_aprobatorios: list[str],
    ) -> UmbralMateria:
        """Insert or update the UmbralMateria for an asignacion."""
        existing = await self.get_by_asignacion(asignacion_id)
        if existing is not None:
            existing.umbral_pct = umbral_pct
            existing.valores_aprobatorios = valores_aprobatorios
            existing.deleted_at = None
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        umbral = UmbralMateria(
            tenant_id=UUID(self._tenant_id),
            asignacion_id=asignacion_id,
            materia_id=materia_id,
            umbral_pct=umbral_pct,
            valores_aprobatorios=valores_aprobatorios,
        )
        self._session.add(umbral)
        await self._session.flush()
        await self._session.refresh(umbral)
        return umbral

    def effective_umbral(self, umbral: UmbralMateria | None) -> tuple[int, list[str]]:
        """Return (umbral_pct, valores_aprobatorios), falling back to defaults."""
        if umbral is None:
            return _DEFAULT_UMBRAL_PCT, _DEFAULT_VALORES
        return umbral.umbral_pct, list(umbral.valores_aprobatorios)
