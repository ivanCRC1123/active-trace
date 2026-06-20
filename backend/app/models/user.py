"""User model — identity anchor for auth and domain operations."""

from typing import Optional

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, EncryptedString


class User(Base, BaseEntityMixin):
    """Authenticated user within a tenant.

    email_cifrado: AES-256-GCM encrypted email (display/recovery).
    email_hash: HMAC-SHA256 of normalized email — blind index for login lookup.
    PII fields (dni_cifrado, cuil_cifrado, cbu_cifrado, alias_cbu_cifrado) are
    also AES-256-GCM via EncryptedString TypeDecorator.
    """

    __tablename__ = "user"

    email_cifrado: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(255), nullable=False)
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    totp_secret: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # PII cifrada con AES-256-GCM (TypeDecorator transparente)
    dni_cifrado: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)
    cuil_cifrado: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)
    cbu_cifrado: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)
    alias_cbu_cifrado: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)

    # Datos de perfil
    banco: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    regional: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    legajo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    legajo_profesional: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    facturador: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )

    def __repr__(self) -> str:
        return f"<User id={self.id}>"
