"""Tenant model — each institution is an isolated tenant.

``Tenant`` is the root of the multi-tenancy hierarchy and therefore
inherits only ``TimeStampedMixin`` and ``SoftDeleteMixin`` (not
``TenantScopedMixin``, which would add a meaningless self-referencing FK).
"""

from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimeStampedMixin


class Tenant(Base, TimeStampedMixin, SoftDeleteMixin):
    """Represents an isolated tenant (institution)."""

    __tablename__ = "tenant"

    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    codigo: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'activo'")
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.id} codigo={self.codigo!r}>"
