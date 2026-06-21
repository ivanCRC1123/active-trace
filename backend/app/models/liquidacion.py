"""Liquidacion — monthly honorarium record per docente × cohorte × period (E19, RN-21/22/37).

Unique per (tenant_id, cohorte_id, usuario_id, rol, periodo).
Once estado=Cerrada the record is immutable — enforced in the service layer.
Monetary amounts use Numeric(12, 2) — never Float (OD-2).
datos_bancarios_incompletos is a technical extension for RN-26 (not in E19 KB).
"""

from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, LiquidacionEstado, RolLiquidable


class Liquidacion(Base, BaseEntityMixin):
    __tablename__ = "liquidacion"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "cohorte_id",
            "usuario_id",
            "rol",
            "periodo",
            name="uq_liquidacion_docente_periodo",
        ),
    )

    cohorte_id: Mapped[UUID] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False),
        nullable=False,
    )
    comisiones: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default=text("'[]'::json"), default=list
    )
    monto_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    monto_plus: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    es_nexo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    excluido_por_factura: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    datos_bancarios_incompletos: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    estado: Mapped[LiquidacionEstado] = mapped_column(
        sa.Enum(LiquidacionEstado, name="liquidacion_estado", create_type=False),
        nullable=False,
        server_default=sa.text("'Abierta'"),
        default=LiquidacionEstado.Abierta,
    )

    def __repr__(self) -> str:
        return (
            f"<Liquidacion usuario={self.usuario_id} periodo={self.periodo!r} "
            f"total={self.total} estado={self.estado}>"
        )
