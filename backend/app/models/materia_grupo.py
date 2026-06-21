"""MateriaGrupo — maps a materia to a plus salary category key (C-18, OD-1).

Resolves the PA-22 gap: SalarioPlus.grupo references a category key (e.g. "PROG")
but Materia has no such field. This table is the tenant-configurable mapping.

One materia can belong to multiple groups (unique per (tenant, materia, grupo)).
"""

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class MateriaGrupo(Base, BaseEntityMixin):
    __tablename__ = "materia_grupo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "materia_id",
            "grupo",
            name="uq_materia_grupo_tenant_materia_grupo",
        ),
    )

    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    grupo: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"<MateriaGrupo materia={self.materia_id} grupo={self.grupo!r}>"
