"""Materia model — subject catalog (E3).

Single source-of-truth catalog for subjects within a tenant (ADR-006).
`codigo` is unique per tenant (uq_materia_tenant_codigo).
The same Materia can be taught across multiple Carreras/Cohortes via
Dictado/Asignacion relationships (C-07+).
"""

import sqlalchemy as sa
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, EstadoBasico


class Materia(Base, BaseEntityMixin):
    __tablename__ = "materia"
    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_materia_tenant_codigo"),
    )

    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    moodle_course_id: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    estado: Mapped[EstadoBasico] = mapped_column(
        sa.Enum(EstadoBasico, name="estado_basico", create_type=False),
        nullable=False,
        server_default="Activa",
    )

    def __repr__(self) -> str:
        return f"<Materia id={self.id} codigo={self.codigo!r}>"
