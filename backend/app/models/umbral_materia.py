"""UmbralMateria model — per-docente approval threshold per materia (E8).

One UmbralMateria per Asignacion (unique constraint on asignacion_id).
An Asignacion encodes (usuario_id × materia_id × cohorte_id), so the
threshold scope is (docente × materia), satisfying RN-03 / RN-04.

`valores_aprobatorios` defaults to RN-02 canonical passing values.
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin

_DEFAULT_VALORES = ["Satisfactorio", "Supera lo esperado"]


class UmbralMateria(Base, BaseEntityMixin):
    __tablename__ = "umbral_materia"

    # FK covers usuario_id + materia_id (+ cohorte_id) in one column.
    asignacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    # 60 = 60% of the 0–100 scale assumed for nota_numerica (RN-03).
    umbral_pct: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("60")
    )
    valores_aprobatorios: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[\"Satisfactorio\",\"Supera lo esperado\"]'::jsonb")
    )

    def __repr__(self) -> str:
        return (
            f"<UmbralMateria id={self.id} asignacion_id={self.asignacion_id} "
            f"umbral_pct={self.umbral_pct}>"
        )
