"""HiloParticipante — join entre HiloMensaje y User (E-C20-2, C-20 F11.2)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.core.database import Base
from app.models.base import TenantScopedMixin


class HiloParticipante(Base, TenantScopedMixin):
    """Join table: un usuario participa en un hilo.

    Join table inmutable: solo tiene id + created_at (sin updated_at).
    ultimo_leido_at se actualiza al marcar el hilo como leído.
    """

    __tablename__ = "hilo_participante"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=None,
    )
    hilo_id: Mapped[UUID] = mapped_column(
        ForeignKey("hilo_mensaje.id", ondelete="CASCADE"), nullable=False
    )
    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    ultimo_leido_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("hilo_id", "usuario_id", name="uq_hilo_participante"),
        Index("idx_hilo_participante_hilo", "hilo_id"),
        Index("idx_hilo_participante_usuario", "tenant_id", "usuario_id"),
    )
