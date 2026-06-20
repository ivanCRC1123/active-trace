"""EntradaPadron model — single student row in a padrón version (E6).

PII: only `email_cifrado` (AES-256-GCM via EncryptedString) + `email_hash`
(HMAC-SHA256 blind index) are protected. nombre/apellidos/comision/regional
are stored in plaintext as per KB §E6.

`usuario_id` is nullable: a student can appear in the padrón before having
a system account. Auto-link on import resolves it when possible.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, EncryptedString


class EntradaPadron(Base, BaseEntityMixin):
    __tablename__ = "entrada_padron"

    version_id: Mapped[UUID] = mapped_column(
        ForeignKey("version_padron.id", ondelete="RESTRICT"), nullable=False
    )
    usuario_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    apellidos: Mapped[str] = mapped_column(String(255), nullable=False)
    email_cifrado: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    comision: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    regional: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<EntradaPadron id={self.id} version_id={self.version_id}>"
