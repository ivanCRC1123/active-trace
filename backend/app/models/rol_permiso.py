"""RolPermiso model — role-permission assignment matrix.

Links a Rol to a Permiso within a tenant, with an optional scope
marker (``'all'`` or ``'own'``). The same permission can be granted
to multiple roles, possibly with different scopes.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class RolPermiso(Base, BaseEntityMixin):
    """Assignment of a permission to a role with a scope marker."""

    __tablename__ = "rol_permiso"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "rol_id", "permiso_id",
            name="uq_rol_permiso_tenant_rol_permiso",
        ),
    )

    rol_id: Mapped[UUID] = mapped_column(
        ForeignKey("rol.id", ondelete="CASCADE"),
        nullable=False,
    )
    permiso_id: Mapped[UUID] = mapped_column(
        ForeignKey("permiso.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(
        String(10), nullable=False, default="all",
    )

    def __repr__(self) -> str:
        return (
            f"<RolPermiso rol_id={self.rol_id} "
            f"permiso_id={self.permiso_id} scope={self.scope!r}>"
        )
