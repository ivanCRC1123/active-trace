"""Tarea — tarea interna del equipo docente (E12, C-16).

contexto_id es una referencia blanda opaca (sin FK): puede apuntar a cualquier
entidad del dominio. La validación de existencia es responsabilidad del caller.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin

ESTADO_PENDIENTE    = "Pendiente"
ESTADO_EN_PROGRESO  = "En progreso"
ESTADO_RESUELTA     = "Resuelta"
ESTADO_CANCELADA    = "Cancelada"

ESTADOS_VALIDOS = {ESTADO_PENDIENTE, ESTADO_EN_PROGRESO, ESTADO_RESUELTA, ESTADO_CANCELADA}
ESTADOS_TERMINALES = {ESTADO_RESUELTA, ESTADO_CANCELADA}


class Tarea(Base, BaseEntityMixin):
    __tablename__ = "tarea"

    materia_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("materia.id", ondelete="SET NULL"), nullable=True
    )
    asignado_a: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    asignado_por: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'Pendiente'"),
        default=ESTADO_PENDIENTE,
    )
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    # Referencia blanda sin FK — ver D-C16-6 en design.md
    contexto_id: Mapped[Optional[UUID]] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_tarea_tenant_id", "tenant_id"),
        Index("ix_tarea_tenant_asignado_a", "tenant_id", "asignado_a"),
        Index("ix_tarea_tenant_asignado_por", "tenant_id", "asignado_por"),
        Index("ix_tarea_tenant_estado", "tenant_id", "estado"),
    )
