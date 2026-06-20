"""Carrera model — academic program catalog (E1).

Single catalog of academic programs per tenant.
`codigo` is unique within a tenant (uq_carrera_tenant_codigo).
An inactive Carrera blocks creation of new Cohortes.
"""

import sqlalchemy as sa
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, EstadoBasico


class Carrera(Base, BaseEntityMixin):
    __tablename__ = "carrera"
    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_carrera_tenant_codigo"),
    )

    codigo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[EstadoBasico] = mapped_column(
        sa.Enum(EstadoBasico, name="estado_basico", create_type=False),
        nullable=False,
        server_default="Activa",
    )

    def __repr__(self) -> str:
        return f"<Carrera id={self.id} codigo={self.codigo!r}>"
