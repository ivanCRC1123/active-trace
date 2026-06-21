"""SalarioPlus — additional salary per (category group × role) with temporal validity (E18, RN-33).

The 'grupo' key matches MateriaGrupo.grupo to determine which materias generate this plus.
Only one entry may be active per (tenant_id, grupo, rol) at any given time — service-enforced.
Monetary amounts use Numeric(12, 2) — never Float (OD-2).
"""

from datetime import date
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, RolLiquidable


class SalarioPlus(Base, BaseEntityMixin):
    __tablename__ = "salario_plus"

    grupo: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rol: Mapped[RolLiquidable] = mapped_column(
        sa.Enum(RolLiquidable, name="rol_liquidable", create_type=False),
        nullable=False,
        index=True,
    )
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    monto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<SalarioPlus grupo={self.grupo!r} rol={self.rol} monto={self.monto}>"
