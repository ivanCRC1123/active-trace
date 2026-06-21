"""HiloMensaje — cabecera de hilo de mensajería interna (E-C20-1, C-20 F11.2)."""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class HiloMensaje(Base, BaseEntityMixin):
    __tablename__ = "hilo_mensaje"

    asunto: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        Index("idx_hilo_tenant", "tenant_id"),
        Index("idx_hilo_tenant_active", "tenant_id", "deleted_at"),
    )
