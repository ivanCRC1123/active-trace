"""FechaAcademica model — academic calendar dates for evaluations (E15).

One record per evaluative instance: (tenant, materia, cohorte, tipo, numero, periodo).
``periodo`` is a free-form string (e.g. "2026-1", "2026-2").
"""

from datetime import date

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from uuid import UUID

from app.core.database import Base
from app.models.base import BaseEntityMixin, TipoEvaluacion


class FechaAcademica(Base, BaseEntityMixin):
    __tablename__ = "fecha_academica"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "materia_id", "cohorte_id", "tipo", "numero", "periodo",
            name="uq_fecha_academica_instancia",
        ),
    )

    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    cohorte_id: Mapped[UUID] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    tipo: Mapped[TipoEvaluacion] = mapped_column(
        sa.Enum(TipoEvaluacion, name="tipo_evaluacion", create_type=False),
        nullable=False,
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    periodo: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha: Mapped[date] = mapped_column(sa.Date, nullable=False)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)

    def __repr__(self) -> str:
        return f"<FechaAcademica id={self.id} tipo={self.tipo} numero={self.numero} periodo={self.periodo!r}>"
