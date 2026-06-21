"""TareaRepository — tenant-scoped queries for Tarea (C-16)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from app.models.tarea import Tarea
from app.models.user import User
from app.repositories.base import BaseRepository
from app.schemas.tareas import TareaFiltros, MisTareasFiltros


@dataclass
class TareaConUsuarios:
    id: UUID
    tenant_id: UUID
    materia_id: UUID | None
    asignado_a_id: UUID
    asignado_a_nombre: str
    asignado_a_apellidos: str
    asignado_por_id: UUID
    asignado_por_nombre: str
    asignado_por_apellidos: str
    estado: str
    descripcion: str
    contexto_id: UUID | None
    created_at: datetime
    updated_at: datetime


class TareaRepository(BaseRepository[Tarea]):

    @property
    def model_class(self) -> type[Tarea]:
        return Tarea

    def _base_con_usuarios_stmt(self) -> sa.Select:
        UserA = aliased(User, name="ua")  # asignado_a
        UserP = aliased(User, name="up")  # asignado_por
        return (
            select(
                Tarea.id,
                Tarea.tenant_id,
                Tarea.materia_id,
                Tarea.asignado_a.label("asignado_a_id"),
                UserA.nombre.label("asignado_a_nombre"),
                UserA.apellidos.label("asignado_a_apellidos"),
                Tarea.asignado_por.label("asignado_por_id"),
                UserP.nombre.label("asignado_por_nombre"),
                UserP.apellidos.label("asignado_por_apellidos"),
                Tarea.estado,
                Tarea.descripcion,
                Tarea.contexto_id,
                Tarea.created_at,
                Tarea.updated_at,
            )
            .join(UserA, UserA.id == Tarea.asignado_a)
            .join(UserP, UserP.id == Tarea.asignado_por)
            .where(
                Tarea.tenant_id == self._tenant_id,
                Tarea.deleted_at.is_(None),
            )
        )

    @staticmethod
    def _row_to_tcu(row) -> TareaConUsuarios:
        return TareaConUsuarios(
            id=row.id,
            tenant_id=row.tenant_id,
            materia_id=row.materia_id,
            asignado_a_id=row.asignado_a_id,
            asignado_a_nombre=row.asignado_a_nombre,
            asignado_a_apellidos=row.asignado_a_apellidos,
            asignado_por_id=row.asignado_por_id,
            asignado_por_nombre=row.asignado_por_nombre,
            asignado_por_apellidos=row.asignado_por_apellidos,
            estado=row.estado,
            descripcion=row.descripcion,
            contexto_id=row.contexto_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def list_by_asignado_a(
        self,
        usuario_id: UUID,
        filtros: MisTareasFiltros,
    ) -> list[TareaConUsuarios]:
        stmt = self._base_con_usuarios_stmt().where(Tarea.asignado_a == usuario_id)
        if filtros.estado is not None:
            stmt = stmt.where(Tarea.estado == filtros.estado)
        if filtros.materia_id is not None:
            stmt = stmt.where(Tarea.materia_id == filtros.materia_id)
        stmt = stmt.limit(filtros.limit).offset(filtros.offset)
        rows = (await self._session.execute(stmt)).all()
        return [self._row_to_tcu(r) for r in rows]

    async def list_tareas(
        self,
        filtros: TareaFiltros,
        scope_user_id: UUID | None = None,
    ) -> list[TareaConUsuarios]:
        stmt = self._base_con_usuarios_stmt()
        if scope_user_id is not None:
            stmt = stmt.where(
                or_(
                    Tarea.asignado_a == scope_user_id,
                    Tarea.asignado_por == scope_user_id,
                )
            )
        if filtros.asignado_a is not None:
            stmt = stmt.where(Tarea.asignado_a == filtros.asignado_a)
        if filtros.asignado_por is not None:
            stmt = stmt.where(Tarea.asignado_por == filtros.asignado_por)
        if filtros.materia_id is not None:
            stmt = stmt.where(Tarea.materia_id == filtros.materia_id)
        if filtros.estado is not None:
            stmt = stmt.where(Tarea.estado == filtros.estado)
        if filtros.q is not None:
            stmt = stmt.where(Tarea.descripcion.ilike(f"%{filtros.q}%"))
        stmt = stmt.limit(filtros.limit).offset(filtros.offset)
        rows = (await self._session.execute(stmt)).all()
        return [self._row_to_tcu(r) for r in rows]

    async def get_con_usuarios(self, tarea_id: UUID) -> TareaConUsuarios | None:
        stmt = self._base_con_usuarios_stmt().where(Tarea.id == tarea_id)
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return self._row_to_tcu(row)

    async def get_raw(self, tarea_id: UUID) -> Tarea | None:
        """Return the raw Tarea ORM object (for mutations)."""
        return await self.get_by_id(tarea_id)
