"""Permiso model — fine-grained permission definitions.

Each row defines a single permission in ``modulo:accion`` format
(e.g., ``calificaciones:importar``). Permissions are data-driven
and tenant-scoped.
"""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class Permiso(Base, BaseEntityMixin):
    """A fine-grained permission within a tenant (e.g., ``calificaciones:importar``)."""

    __tablename__ = "permiso"
    __table_args__ = (
        UniqueConstraint("tenant_id", "codigo", name="uq_permiso_tenant_codigo"),
    )

    codigo: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    descripcion: Mapped[str] = mapped_column(
        String(255), nullable=True, default=None,
    )
    modulo: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Permiso id={self.id} codigo={self.codigo!r}>"
