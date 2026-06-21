"""SalarioBase — base salary per liquidable role with temporal validity (E17, RN-32).

Only one entry may be active per (tenant_id, rol) at any given time —
enforced in the service layer (not a DB constraint, to allow history).
Monetary amounts use Numeric(12, 2) — never Float (OD-2).
"""

from datetime import date
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Date, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, RolLiquidable


class SalarioBase(Base, BaseEntityMixin):
    __tablename__ = "salario_base"

    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False),
        nullable=False,
        index=True,
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<SalarioBase rol={self.rol} monto={self.monto} desde={self.desde}>"
