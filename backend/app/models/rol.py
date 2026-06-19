"""Rol model — domain role definitions.

Each row represents a named role (e.g., ADMIN, PROFESOR) within a tenant.
Roles are data-driven: tenants can create and manage their own role set.
"""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class Rol(Base, BaseEntityMixin):
    """A named role within a tenant (e.g., ADMIN, PROFESOR, ALUMNO)."""

    __tablename__ = "rol"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nombre", name="uq_rol_tenant_nombre"),
    )

    nombre: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    descripcion: Mapped[str] = mapped_column(
        String(255), nullable=True, default=None,
    )

    def __repr__(self) -> str:
        return f"<Rol id={self.id} nombre={self.nombre!r}>"
