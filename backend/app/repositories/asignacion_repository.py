"""AsignacionRepository — tenant-scoped queries for Asignacion with vigencia filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from app.models.asignacion import Asignacion
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.materia import Materia
from app.models.rol import Rol
from app.models.user import User
from app.repositories.base import BaseRepository


@dataclass
class AsignacionConNombres:
    id: UUID
    tenant_id: UUID
    usuario_id: UUID
    usuario_nombre: str
    usuario_apellidos: str
    rol_id: UUID
    rol_nombre: str
    materia_id: UUID | None
    materia_nombre: str | None
    carrera_id: UUID | None
    carrera_nombre: str | None
    cohorte_id: UUID | None
    cohorte_nombre: str | None
    comisiones: list
    responsable_id: UUID | None
    desde: date
    hasta: date | None


class AsignacionRepository(BaseRepository[Asignacion]):

    @property
    def model_class(self) -> type[Asignacion]:
        return Asignacion

    # ── Existing vigencia filters (C-07) ─────────────────────────────

    async def list_vigentes(self, today: date) -> Sequence[Asignacion]:
        stmt = select(Asignacion).where(
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.deleted_at.is_(None),
            Asignacion.desde <= today,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= today),
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_vencidas(self, today: date) -> Sequence[Asignacion]:
        stmt = select(Asignacion).where(
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.deleted_at.is_(None),
            or_(Asignacion.desde > today, Asignacion.hasta < today),
        )
        return (await self._session.execute(stmt)).scalars().all()

    # ── C-08: queries con nombres resueltos ──────────────────────────

    def _base_con_nombres_stmt(self) -> sa.Select:
        UserAlias = aliased(User)
        return (
            select(
                Asignacion.id,
                Asignacion.tenant_id,
                Asignacion.usuario_id,
                UserAlias.nombre.label("usuario_nombre"),
                UserAlias.apellidos.label("usuario_apellidos"),
                Asignacion.rol_id,
                Rol.nombre.label("rol_nombre"),
                Asignacion.materia_id,
                Materia.nombre.label("materia_nombre"),
                Asignacion.carrera_id,
                Carrera.nombre.label("carrera_nombre"),
                Asignacion.cohorte_id,
                Cohorte.nombre.label("cohorte_nombre"),
                Asignacion.comisiones,
                Asignacion.responsable_id,
                Asignacion.desde,
                Asignacion.hasta,
            )
            .join(UserAlias, UserAlias.id == Asignacion.usuario_id)
            .join(Rol, Rol.id == Asignacion.rol_id)
            .outerjoin(Materia, Materia.id == Asignacion.materia_id)
            .outerjoin(Carrera, Carrera.id == Asignacion.carrera_id)
            .outerjoin(Cohorte, Cohorte.id == Asignacion.cohorte_id)
            .where(
                Asignacion.tenant_id == self._tenant_id,
                Asignacion.deleted_at.is_(None),
            )
        )

    @staticmethod
    def _row_to_acn(row) -> AsignacionConNombres:
        return AsignacionConNombres(
            id=row.id,
            tenant_id=row.tenant_id,
            usuario_id=row.usuario_id,
            usuario_nombre=row.usuario_nombre,
            usuario_apellidos=row.usuario_apellidos,
            rol_id=row.rol_id,
            rol_nombre=row.rol_nombre,
            materia_id=row.materia_id,
            materia_nombre=row.materia_nombre,
            carrera_id=row.carrera_id,
            carrera_nombre=row.carrera_nombre,
            cohorte_id=row.cohorte_id,
            cohorte_nombre=row.cohorte_nombre,
            comisiones=row.comisiones if row.comisiones is not None else [],
            responsable_id=row.responsable_id,
            desde=row.desde,
            hasta=row.hasta,
        )

    async def list_by_usuario(
        self,
        usuario_id: UUID,
        *,
        materia_id: UUID | None = None,
        carrera_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        rol: str | None = None,
        estado_vigencia: str | None = None,
        today: date | None = None,
    ) -> list[AsignacionConNombres]:
        stmt = self._base_con_nombres_stmt().where(Asignacion.usuario_id == usuario_id)

        if materia_id is not None:
            stmt = stmt.where(Asignacion.materia_id == materia_id)
        if carrera_id is not None:
            stmt = stmt.where(Asignacion.carrera_id == carrera_id)
        if cohorte_id is not None:
            stmt = stmt.where(Asignacion.cohorte_id == cohorte_id)
        if rol is not None:
            stmt = stmt.where(Rol.nombre == rol)
        if estado_vigencia is not None and today is not None:
            stmt = _apply_vigencia_filter(stmt, estado_vigencia, today)

        rows = (await self._session.execute(stmt)).all()
        return [self._row_to_acn(r) for r in rows]

    async def list_equipo(
        self,
        *,
        materia_id: UUID | None = None,
        carrera_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        usuario_id: UUID | None = None,
        responsable_id: UUID | None = None,
        rol: str | None = None,
        estado_vigencia: str | None = None,
        today: date | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AsignacionConNombres]:
        stmt = self._base_con_nombres_stmt()

        if materia_id is not None:
            stmt = stmt.where(Asignacion.materia_id == materia_id)
        if carrera_id is not None:
            stmt = stmt.where(Asignacion.carrera_id == carrera_id)
        if cohorte_id is not None:
            stmt = stmt.where(Asignacion.cohorte_id == cohorte_id)
        if usuario_id is not None:
            stmt = stmt.where(Asignacion.usuario_id == usuario_id)
        if responsable_id is not None:
            stmt = stmt.where(Asignacion.responsable_id == responsable_id)
        if rol is not None:
            stmt = stmt.where(Rol.nombre == rol)
        if estado_vigencia is not None and today is not None:
            stmt = _apply_vigencia_filter(stmt, estado_vigencia, today)

        stmt = stmt.limit(limit).offset(offset)
        rows = (await self._session.execute(stmt)).all()
        return [self._row_to_acn(r) for r in rows]

    # ── C-08: clonar helpers ──────────────────────────────────────────

    async def list_vigentes_por_contexto(
        self,
        *,
        materia_id: UUID | None,
        carrera_id: UUID | None,
        cohorte_id: UUID | None,
        today: date,
    ) -> Sequence[Asignacion]:
        conditions = [
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.deleted_at.is_(None),
            Asignacion.desde <= today,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= today),
        ]
        if materia_id is not None:
            conditions.append(Asignacion.materia_id == materia_id)
        if carrera_id is not None:
            conditions.append(Asignacion.carrera_id == carrera_id)
        if cohorte_id is not None:
            conditions.append(Asignacion.cohorte_id == cohorte_id)

        stmt = select(Asignacion).where(*conditions)
        return (await self._session.execute(stmt)).scalars().all()

    async def existe_vigente_en_destino(
        self,
        *,
        usuario_id: UUID,
        rol_id: UUID,
        materia_id: UUID | None,
        carrera_id: UUID | None,
        cohorte_id: UUID | None,
        today: date,
    ) -> bool:
        conditions = [
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.deleted_at.is_(None),
            Asignacion.usuario_id == usuario_id,
            Asignacion.rol_id == rol_id,
            Asignacion.desde <= today,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= today),
        ]
        if materia_id is not None:
            conditions.append(Asignacion.materia_id == materia_id)
        else:
            conditions.append(Asignacion.materia_id.is_(None))
        if carrera_id is not None:
            conditions.append(Asignacion.carrera_id == carrera_id)
        else:
            conditions.append(Asignacion.carrera_id.is_(None))
        if cohorte_id is not None:
            conditions.append(Asignacion.cohorte_id == cohorte_id)
        else:
            conditions.append(Asignacion.cohorte_id.is_(None))

        stmt = select(sa.literal(1)).where(*conditions).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    # ── C-18: asignaciones activas en un período calendario ──────────────

    async def list_activas_en_cohorte_periodo(
        self, cohorte_id: UUID, periodo_desde: date, periodo_hasta: date
    ) -> list[AsignacionConNombres]:
        """Return AsignacionConNombres in a cohorte that overlap [periodo_desde, periodo_hasta].

        Overlap: desde <= periodo_hasta AND (hasta IS NULL OR hasta >= periodo_desde).
        """
        stmt = self._base_con_nombres_stmt().where(
            Asignacion.cohorte_id == cohorte_id,
            Asignacion.desde <= periodo_hasta,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= periodo_desde),
        )
        rows = (await self._session.execute(stmt)).all()
        return [self._row_to_acn(r) for r in rows]

    # ── C-08: bulk update vigencia ────────────────────────────────────

    async def bulk_update_vigencia(
        self,
        *,
        materia_id: UUID | None,
        carrera_id: UUID | None,
        cohorte_id: UUID | None,
        desde: date,
        hasta: date | None,
    ) -> int:
        conditions = [
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.deleted_at.is_(None),
        ]
        if materia_id is not None:
            conditions.append(Asignacion.materia_id == materia_id)
        if carrera_id is not None:
            conditions.append(Asignacion.carrera_id == carrera_id)
        if cohorte_id is not None:
            conditions.append(Asignacion.cohorte_id == cohorte_id)

        stmt = (
            sa.update(Asignacion)
            .where(*conditions)
            .values(desde=desde, hasta=hasta)
            .returning(Asignacion.id)
        )
        result = await self._session.execute(stmt)
        return len(result.all())


# ── Helpers ───────────────────────────────────────────────────────────

def _apply_vigencia_filter(stmt: sa.Select, estado_vigencia: str, today: date) -> sa.Select:
    if estado_vigencia == "Vigente":
        return stmt.where(
            Asignacion.desde <= today,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= today),
        )
    # Vencida
    return stmt.where(
        or_(Asignacion.desde > today, Asignacion.hasta < today)
    )
