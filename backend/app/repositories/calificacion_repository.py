"""CalificacionRepository — tenant-scoped queries for Calificacion (E7)."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asignacion import Asignacion
from app.models.calificacion import Calificacion, OrigenCalificacion
from app.repositories.base import BaseRepository


class CalificacionRepository(BaseRepository[Calificacion]):

    @property
    def model_class(self) -> type[Calificacion]:
        return Calificacion

    async def list_by_asignacion(self, asignacion_id: UUID) -> Sequence[Calificacion]:
        stmt = select(Calificacion).where(
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.asignacion_id == asignacion_id,
            Calificacion.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_by_asignacion_actividad(
        self, asignacion_id: UUID, actividades: list[str]
    ) -> Sequence[Calificacion]:
        stmt = select(Calificacion).where(
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.asignacion_id == asignacion_id,
            Calificacion.actividad.in_(actividades),
            Calificacion.deleted_at.is_(None),
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def upsert_calificacion(
        self,
        *,
        asignacion_id: UUID,
        entrada_padron_id: UUID,
        materia_id: UUID,
        actividad: str,
        nota_numerica: Decimal | None,
        nota_textual: str | None,
        aprobado: bool,
        origen: OrigenCalificacion,
    ) -> Calificacion:
        """Insert or update a single calificacion row."""
        existing = await self._get_by_key(asignacion_id, entrada_padron_id, actividad)
        if existing is not None:
            existing.nota_numerica = nota_numerica
            existing.nota_textual = nota_textual
            existing.aprobado = aprobado
            existing.origen = origen
            existing.deleted_at = None
            await self._session.flush()
            await self._session.refresh(existing)
            return existing

        cal = Calificacion(
            tenant_id=UUID(self._tenant_id),
            asignacion_id=asignacion_id,
            entrada_padron_id=entrada_padron_id,
            materia_id=materia_id,
            actividad=actividad,
            nota_numerica=nota_numerica,
            nota_textual=nota_textual,
            aprobado=aprobado,
            origen=origen,
        )
        self._session.add(cal)
        await self._session.flush()
        await self._session.refresh(cal)
        return cal

    async def recalc_aprobado_para_asignacion(
        self,
        asignacion_id: UUID,
        umbral_pct: int,
        valores_aprobatorios: list[str],
    ) -> int:
        """Recalculate `aprobado` for all calificaciones of an asignacion.

        Returns the number of rows updated.

        Scale assumption (RN-03): nota_numerica is on 0–100 scale;
        aprobado = nota_numerica >= umbral_pct.
        """
        rows = await self.list_by_asignacion(asignacion_id)
        count = 0
        for cal in rows:
            new_aprobado = _derive_aprobado(
                cal.nota_numerica, cal.nota_textual, umbral_pct, valores_aprobatorios
            )
            if cal.aprobado != new_aprobado:
                cal.aprobado = new_aprobado
                count += 1
        if count:
            await self._session.flush()
        return count

    async def vaciar_por_usuario_materia(
        self,
        usuario_id: UUID,
        materia_id: UUID,
    ) -> int:
        """Soft-delete all calificaciones for (usuario_id × materia_id).

        Joins through Asignacion to resolve the scope (RN-04).
        Returns the count of soft-deleted rows.
        """
        asig_ids_stmt = select(Asignacion.id).where(
            Asignacion.tenant_id == UUID(self._tenant_id),
            Asignacion.usuario_id == usuario_id,
            Asignacion.materia_id == materia_id,
            Asignacion.deleted_at.is_(None),
        )
        asig_ids = (await self._session.execute(asig_ids_stmt)).scalars().all()
        if not asig_ids:
            return 0

        stmt = select(Calificacion).where(
            Calificacion.tenant_id == UUID(self._tenant_id),
            Calificacion.asignacion_id.in_(asig_ids),
            Calificacion.materia_id == materia_id,
            Calificacion.deleted_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        from sqlalchemy.sql import func  # noqa: PLC0415
        for row in rows:
            row.deleted_at = func.now()
        await self._session.flush()
        return len(rows)

    # ── Private ────────────────────────────────────────────────────────────────

    async def _get_by_key(
        self,
        asignacion_id: UUID,
        entrada_padron_id: UUID,
        actividad: str,
    ) -> Calificacion | None:
        stmt = select(Calificacion).where(
            Calificacion.asignacion_id == asignacion_id,
            Calificacion.entrada_padron_id == entrada_padron_id,
            Calificacion.actividad == actividad,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()


def _derive_aprobado(
    nota_numerica: Decimal | None,
    nota_textual: str | None,
    umbral_pct: int,
    valores_aprobatorios: list[str],
) -> bool:
    """Derive `aprobado` from grade data and threshold config.

    Scale assumption (RN-03): nota_numerica is in the range 0–100.
    aprobado = nota_numerica >= umbral_pct  (e.g. 75 >= 60 → True).
    """
    if nota_numerica is not None:
        return nota_numerica >= umbral_pct
    if nota_textual is not None:
        return nota_textual in valores_aprobatorios
    return False
