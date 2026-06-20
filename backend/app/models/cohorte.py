"""Cohorte model — academic cohort (E2).

Cohorte belongs to one Carrera (carrera_id FK with RESTRICT).
Unique per (tenant_id, carrera_id, nombre).
`vig_hasta` is nullable — a null value means the cohort has no end date.
"""

import sqlalchemy as sa
from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, EstadoBasico


class Cohorte(Base, BaseEntityMixin):
    __tablename__ = "cohorte"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "carrera_id", "nombre",
            name="uq_cohorte_tenant_carrera_nombre",
        ),
    )

    carrera_id: Mapped[UUID] = mapped_column(
        ForeignKey("carrera.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    vig_desde: Mapped[date] = mapped_column(Date, nullable=False)
    vig_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoBasico] = mapped_column(
        sa.Enum(EstadoBasico, name="estado_basico", create_type=False),
        nullable=False,
        server_default="Activa",
    )

    def __repr__(self) -> str:
        return f"<Cohorte id={self.id} nombre={self.nombre!r}>"
