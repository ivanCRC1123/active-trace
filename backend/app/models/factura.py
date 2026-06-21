"""Factura — invoice presented by a docente with facturador=True (E20, RN-39/40).

referencia_archivo is an opaque string (same pattern as ProgramaMateria).
tamano_kb uses Numeric(12, 3) for KB precision — never Float.
Transition Pendiente→Abonada is unidirectional; enforced in service layer.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.base import BaseEntityMixin, FacturaEstado


class Factura(Base, BaseEntityMixin):
    __tablename__ = "factura"

    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)
    detalle: Mapped[str] = mapped_column(Text, nullable=False)
    referencia_archivo: Mapped[str] = mapped_column(Text, nullable=False)
    tamano_kb: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    estado: Mapped[FacturaEstado] = mapped_column(
        sa.Enum(FacturaEstado, name="factura_estado", create_type=False),
        nullable=False,
        server_default=sa.text("'Pendiente'"),
        default=FacturaEstado.Pendiente,
    )
    cargada_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    abonada_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"<Factura usuario={self.usuario_id} periodo={self.periodo!r} estado={self.estado}>"
