"""Calificacion model — grade record per student per activity (E7).

`asignacion_id` tracks the docente who imported this batch (RN-04 scope:
usuario_id × materia_id via the Asignacion FK).

`aprobado` is a derived/stored field for query efficiency (E7):
  - If nota_numerica is set: nota_numerica >= umbral_pct (scale 0–100, RN-03).
  - If nota_textual only: textual value ∈ valores_aprobatorios of UmbralMateria.
When UmbralMateria changes, calificaciones for that asignacion are recalculated
(see CalificacionRepository.recalc_aprobado_para_asignacion).
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class OrigenCalificacion(str, enum.Enum):
    Importado = "Importado"
    Manual = "Manual"


class Calificacion(Base, BaseEntityMixin):
    __tablename__ = "calificacion"

    asignacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=False
    )
    entrada_padron_id: Mapped[UUID] = mapped_column(
        ForeignKey("entrada_padron.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    actividad: Mapped[str] = mapped_column(String(500), nullable=False)
    nota_numerica: Mapped[Optional[Decimal]] = mapped_column(
        sa.Numeric(precision=10, scale=2), nullable=True
    )
    nota_textual: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Stored derived field — see module docstring for recalc contract.
    aprobado: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    origen: Mapped[OrigenCalificacion] = mapped_column(
        sa.Enum(OrigenCalificacion, name="origen_calificacion"), nullable=False
    )
    importado_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:
        return (
            f"<Calificacion id={self.id} asignacion_id={self.asignacion_id} "
            f"actividad={self.actividad!r} aprobado={self.aprobado}>"
        )
