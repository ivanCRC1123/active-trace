"""MensajeInterno — cuerpo de mensaje en un hilo (E-C20-3, C-20 F11.2).

remitente_id es nullable: NULL indica mensaje del sistema (sin autor humano).
Sin updated_at — los mensajes son inmutables una vez creados.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from app.core.database import Base
from app.models.base import SoftDeleteMixin, TenantScopedMixin


class MensajeInterno(Base, SoftDeleteMixin, TenantScopedMixin):
    __tablename__ = "mensaje_interno"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=None,
    )
    hilo_id: Mapped[UUID] = mapped_column(
        ForeignKey("hilo_mensaje.id", ondelete="CASCADE"), nullable=False
    )
    remitente_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_mensaje_hilo", "hilo_id", "created_at"),
        Index("idx_mensaje_tenant", "tenant_id"),
    )
