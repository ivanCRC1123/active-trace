"""UserRol model — user-to-role assignment.

Links a User to a Rol within a tenant. A user can have multiple roles;
the effective permissions are the union of all assigned roles.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class UserRol(Base, BaseEntityMixin):
    """Assignment of a role to a user within a tenant."""

    __tablename__ = "user_rol"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", "rol_id",
            name="uq_user_rol_tenant_user_rol",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    )
    rol_id: Mapped[UUID] = mapped_column(
        ForeignKey("rol.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<UserRol user_id={self.user_id} "
            f"rol_id={self.rol_id}>"
        )
