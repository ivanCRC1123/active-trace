"""RecoveryToken model — single-use password recovery token.

Does NOT inherit TenantScopedMixin because forgot/reset are public
endpoints without session. ``tenant_id`` is included manually for
isolation and traceability.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TimeStampedMixin


class RecoveryToken(Base, TimeStampedMixin, SoftDeleteMixin):
    """A single-use recovery token for password reset.

    Inherits ``id``, ``created_at``, ``updated_at`` (TimeStampedMixin)
    and ``deleted_at`` (SoftDeleteMixin). Has its own ``tenant_id``
    FK but does NOT inherit TenantScopedMixin.
    """

    __tablename__ = "recovery_token"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<RecoveryToken id={self.id} "
            f"user_id={self.user_id} "
            f"used={self.used_at is not None}>"
        )
