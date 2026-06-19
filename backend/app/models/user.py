"""User model — minimal identity for authentication.

Will be expanded in C-07 with profile, legajo, roles, etc.
"""

from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class User(Base, BaseEntityMixin):
    """Represents an authenticated user within a tenant.

    The User is the identity anchor for all auth operations.
    ``email`` is globally unique for simplicity; password hashes
    use Argon2id; ``totp_secret`` is AES-256 encrypted.
    """

    __tablename__ = "user"

    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellido: Mapped[str] = mapped_column(String(100), nullable=False)
    is_2fa_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )
    totp_secret: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default=None,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
