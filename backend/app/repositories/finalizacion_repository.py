"""FinalizacionRepository — CRUD for FinalizacionActividad (C-11)."""

from __future__ import annotations

from typing import TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.calificacion import Calificacion
from app.models.entrada_padron import EntradaPadron
from app.models.finalizacion_actividad import FinalizacionActividad
from app.models.version_padron import VersionPadron
from app.repositories.base import BaseRepository


class SinCorregirRow(TypedDict):
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    actividad: str


class FinalizacionRepository(BaseRepository[FinalizacionActividad]):

    @property
    def model_class(self) -> type[FinalizacionActividad]:
        return FinalizacionActividad

    async def vaciar_por_asignacion_materia(
        self, asignacion_id: UUID, materia_id: UUID
    ) -> int:
        """Soft-delete all finalizacion rows for (asignacion_id × materia_id)."""
        stmt = select(FinalizacionActividad).where(
            FinalizacionActividad.tenant_id == UUID(self._tenant_id),
            FinalizacionActividad.asignacion_id == asignacion_id,
            FinalizacionActividad.materia_id == materia_id,
            FinalizacionActividad.deleted_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        for row in rows:
            row.deleted_at = func.now()
        if rows:
            await self._session.flush()
        return len(rows)

    async def bulk_insert(
        self,
        rows: list[dict],
    ) -> int:
        """Bulk-insert FinalizacionActividad rows. Returns count inserted."""
        objs = [
            FinalizacionActividad(
                tenant_id=UUID(self._tenant_id),
                entrada_padron_id=r["entrada_padron_id"],
                materia_id=r["materia_id"],
                asignacion_id=r["asignacion_id"],
                actividad=r["actividad"],
                finalizado=r["finalizado"],
            )
            for r in rows
        ]
        for obj in objs:
            self._session.add(obj)
        if objs:
            await self._session.flush()
        return len(objs)

    async def count_por_asignacion(
        self, asignacion_id: UUID, materia_id: UUID
    ) -> int:
        """Returns the count of non-deleted rows for this scope."""
        stmt = (
            sa.select(sa.func.count())
            .select_from(FinalizacionActividad)
            .where(
                FinalizacionActividad.tenant_id == UUID(self._tenant_id),
                FinalizacionActividad.asignacion_id == asignacion_id,
                FinalizacionActividad.materia_id == materia_id,
                FinalizacionActividad.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def list_sin_corregir(
        self,
        materia_id: UUID,
        asignacion_id: UUID,
    ) -> list[SinCorregirRow]:
        """Return entries where finalizado=True AND no Calificacion AND textual activity.

        Implements D-C11-7: "sin corregir" = finalizado=True, actividad textual (RN-08),
        no matching Calificacion row.
        """
        # Step 1: collect textual activity names for this scope
        textual_stmt = (
            sa.select(sa.distinct(Calificacion.actividad))
            .where(
                Calificacion.tenant_id == UUID(self._tenant_id),
                Calificacion.materia_id == materia_id,
                Calificacion.asignacion_id == asignacion_id,
                Calificacion.nota_textual.isnot(None),
                Calificacion.deleted_at.is_(None),
            )
        )
        textual_result = await self._session.execute(textual_stmt)
        textual_activities = [r for r, in textual_result.all()]

        if not textual_activities:
            return []

        # Step 2: finalizado=True + textual + no calificacion
        calificacion_exists = (
            sa.select(Calificacion.id)
            .where(
                Calificacion.entrada_padron_id == FinalizacionActividad.entrada_padron_id,
                Calificacion.actividad == FinalizacionActividad.actividad,
                Calificacion.asignacion_id == asignacion_id,
                Calificacion.deleted_at.is_(None),
            )
            .correlate(FinalizacionActividad)
            .exists()
        )

        stmt = (
            sa.select(
                EntradaPadron.id.label("entrada_padron_id"),
                EntradaPadron.nombre,
                EntradaPadron.apellidos,
                EntradaPadron.comision,
                FinalizacionActividad.actividad,
            )
            .join(EntradaPadron, FinalizacionActividad.entrada_padron_id == EntradaPadron.id)
            .where(
                FinalizacionActividad.tenant_id == UUID(self._tenant_id),
                FinalizacionActividad.materia_id == materia_id,
                FinalizacionActividad.asignacion_id == asignacion_id,
                FinalizacionActividad.finalizado.is_(True),
                FinalizacionActividad.actividad.in_(textual_activities),
                FinalizacionActividad.deleted_at.is_(None),
                EntradaPadron.deleted_at.is_(None),
                ~calificacion_exists,
            )
            .order_by(EntradaPadron.apellidos, EntradaPadron.nombre, FinalizacionActividad.actividad)
        )

        result = await self._session.execute(stmt)
        return [
            SinCorregirRow(
                entrada_padron_id=row.entrada_padron_id,
                nombre=row.nombre,
                apellidos=row.apellidos,
                comision=row.comision,
                actividad=row.actividad,
            )
            for row in result.all()
        ]
