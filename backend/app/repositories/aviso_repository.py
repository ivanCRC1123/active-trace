"""AvisoRepository y AckAvisoRepository — C-15 avisos-y-acknowledgment."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, or_, select

from app.models.aviso import AcknowledgmentAviso, AlcanceAviso, Aviso
from app.repositories.base import BaseRepository


class AvisoRepository(BaseRepository[Aviso]):

    @property
    def model_class(self) -> type[Aviso]:
        return Aviso

    async def list_all(self) -> list[Aviso]:
        """Admin view: all non-deleted avisos regardless of vigencia."""
        stmt = (
            select(Aviso)
            .where(
                Aviso.tenant_id == self._tenant_id,
                Aviso.deleted_at.is_(None),
            )
            .order_by(Aviso.orden.asc(), Aviso.inicio_en.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_visibles_para_usuario(
        self,
        *,
        roles: set[str],
        materias: set[UUID],
        cohortes: set[UUID],
        usuario_id: UUID,
        now: datetime,
    ) -> list[Aviso]:
        """Apply RN-18 (vigencia) + RN-20 (scope) + RN-19 (ack exclusion)."""
        # RN-20: build OR scope conditions
        scope_conditions: list = [Aviso.alcance == AlcanceAviso.Global]
        if roles:
            scope_conditions.append(
                and_(Aviso.alcance == AlcanceAviso.PorRol, Aviso.rol_destino.in_(roles))
            )
        if materias:
            scope_conditions.append(
                and_(Aviso.alcance == AlcanceAviso.PorMateria, Aviso.materia_id.in_(materias))
            )
        if cohortes:
            scope_conditions.append(
                and_(Aviso.alcance == AlcanceAviso.PorCohorte, Aviso.cohorte_id.in_(cohortes))
            )
        scope_filter = or_(*scope_conditions)

        # RN-19: exclude already-acked avisos when requiere_ack=True
        ack_exists_stmt = (
            select(AcknowledgmentAviso.id)
            .where(
                AcknowledgmentAviso.aviso_id == Aviso.id,
                AcknowledgmentAviso.usuario_id == usuario_id,
                AcknowledgmentAviso.tenant_id == self._tenant_id,
                AcknowledgmentAviso.deleted_at.is_(None),
            )
            .correlate(Aviso)
        )
        ack_filter = or_(~Aviso.requiere_ack, ~exists(ack_exists_stmt))

        stmt = (
            select(Aviso)
            .where(
                Aviso.tenant_id == self._tenant_id,
                Aviso.deleted_at.is_(None),
                Aviso.activo.is_(True),
                Aviso.inicio_en <= now,   # RN-18: vigencia inicio
                Aviso.fin_en >= now,      # RN-18: vigencia fin
                scope_filter,
                ack_filter,
            )
            .order_by(Aviso.orden.asc(), Aviso.inicio_en.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_confirmaciones(self, aviso_id: UUID) -> int:
        """Count acks for a given aviso (stats endpoint)."""
        stmt = (
            select(AcknowledgmentAviso.id)
            .where(
                AcknowledgmentAviso.aviso_id == aviso_id,
                AcknowledgmentAviso.tenant_id == self._tenant_id,
                AcknowledgmentAviso.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())


class AckAvisoRepository(BaseRepository[AcknowledgmentAviso]):

    @property
    def model_class(self) -> type[AcknowledgmentAviso]:
        return AcknowledgmentAviso

    async def get_by_aviso_usuario(
        self, aviso_id: UUID, usuario_id: UUID
    ) -> AcknowledgmentAviso | None:
        stmt = select(AcknowledgmentAviso).where(
            AcknowledgmentAviso.aviso_id == aviso_id,
            AcknowledgmentAviso.usuario_id == usuario_id,
            AcknowledgmentAviso.tenant_id == self._tenant_id,
            AcknowledgmentAviso.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_ack(
        self, aviso_id: UUID, usuario_id: UUID
    ) -> AcknowledgmentAviso:
        return await self.create({"aviso_id": aviso_id, "usuario_id": usuario_id})
