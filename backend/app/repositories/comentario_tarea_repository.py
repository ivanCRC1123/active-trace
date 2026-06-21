"""ComentarioTareaRepository — queries for ComentarioTarea (C-16)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import aliased

from app.models.comentario_tarea import ComentarioTarea
from app.models.user import User
from app.repositories.base import BaseRepository


@dataclass
class ComentarioConAutor:
    id: UUID
    tarea_id: UUID
    autor_id: UUID
    autor_nombre: str
    autor_apellidos: str
    texto: str
    creado_at: datetime


class ComentarioTareaRepository(BaseRepository[ComentarioTarea]):

    @property
    def model_class(self) -> type[ComentarioTarea]:
        return ComentarioTarea

    async def list_by_tarea(self, tarea_id: UUID) -> list[ComentarioConAutor]:
        UserA = aliased(User, name="autor")
        stmt = (
            select(
                ComentarioTarea.id,
                ComentarioTarea.tarea_id,
                ComentarioTarea.autor_id,
                UserA.nombre.label("autor_nombre"),
                UserA.apellidos.label("autor_apellidos"),
                ComentarioTarea.texto,
                ComentarioTarea.created_at.label("creado_at"),
            )
            .join(UserA, UserA.id == ComentarioTarea.autor_id)
            .where(
                ComentarioTarea.tarea_id == tarea_id,
                ComentarioTarea.tenant_id == self._tenant_id,
                ComentarioTarea.deleted_at.is_(None),
            )
            .order_by(ComentarioTarea.created_at.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            ComentarioConAutor(
                id=r.id,
                tarea_id=r.tarea_id,
                autor_id=r.autor_id,
                autor_nombre=r.autor_nombre,
                autor_apellidos=r.autor_apellidos,
                texto=r.texto,
                creado_at=r.creado_at,
            )
            for r in rows
        ]
