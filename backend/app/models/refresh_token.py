"""RefreshToken model — opaque token with SHA-256 hash in DB.

Supports rotation with family revocation (token reuse detection).
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class RefreshToken(Base, BaseEntityMixin):
    """An opaque refresh token stored as SHA-256 hash.

    ``family_id`` groups tokens from the same login session
    for reuse detection (all tokens in a family are revoked
    when one is reused after rotation).
    """

    __tablename__ = "refresh_token"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
    )
    family_id: Mapped[UUID] = mapped_column(
        nullable=False, index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<RefreshToken id={self.id} "
            f"user_id={self.user_id} "
            f"revoked={self.revoked_at is not None}>"
        )
