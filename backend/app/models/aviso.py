"""Aviso y AcknowledgmentAviso — tablón de avisos institucional (E13, C-15)."""

from __future__ import annotations

import enum
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class AlcanceAviso(str, enum.Enum):
    Global     = "Global"
    PorMateria = "PorMateria"
    PorCohorte = "PorCohorte"
    PorRol     = "PorRol"


class SeveridadAviso(str, enum.Enum):
    Info        = "Info"
    Advertencia = "Advertencia"
    Critico     = "Critico"


class Aviso(Base, BaseEntityMixin):
    __tablename__ = "aviso"

    alcance: Mapped[AlcanceAviso] = mapped_column(
        sa.Enum(AlcanceAviso, name="alcance_aviso", create_type=False),
        nullable=False,
    )
    materia_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=True
    )
    cohorte_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"), nullable=True
    )
    # rol_destino as String(50) — closed catalog enforced at schema layer (Literal), not DB enum
    rol_destino: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    severidad: Mapped[SeveridadAviso] = mapped_column(
        sa.Enum(SeveridadAviso, name="severidad_aviso", create_type=False),
        nullable=False,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    inicio_en: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    fin_en: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    orden: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("true")
    )
    requiere_ack: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.text("false")
    )

    __table_args__ = (
        Index("idx_aviso_tenant", "tenant_id"),
        Index("idx_aviso_vigencia", "tenant_id", "activo", "inicio_en", "fin_en"),
        Index("idx_aviso_alcance", "tenant_id", "alcance"),
    )


class AcknowledgmentAviso(Base, BaseEntityMixin):
    __tablename__ = "acknowledgment_aviso"

    aviso_id: Mapped[UUID] = mapped_column(
        ForeignKey("aviso.id", ondelete="RESTRICT"), nullable=False
    )
    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    # created_at (from BaseEntityMixin) serves as confirmado_at per KB E13

    __table_args__ = (
        UniqueConstraint("tenant_id", "aviso_id", "usuario_id", name="uq_ack_aviso_usuario"),
        Index("idx_ack_aviso_id", "aviso_id"),
        Index("idx_ack_usuario_id", "tenant_id", "usuario_id"),
    )
