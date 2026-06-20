"""ProgramaMateria model — official course document per materia × carrera × cohorte (E16).

``referencia_archivo`` is an opaque text reference to an external storage service.
One program per (tenant, materia, carrera, cohorte) combination — unique constraint enforced.
"""

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.models.base import BaseEntityMixin
from uuid import UUID


class ProgramaMateria(Base, BaseEntityMixin):
    __tablename__ = "programa_materia"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "materia_id", "carrera_id", "cohorte_id",
            name="uq_programa_materia_tenant_materia_carrera_cohorte",
        ),
    )

    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    carrera_id: Mapped[UUID] = mapped_column(
        ForeignKey("carrera.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    cohorte_id: Mapped[UUID] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    referencia_archivo: Mapped[str] = mapped_column(Text, nullable=False)
    cargado_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ProgramaMateria id={self.id} materia={self.materia_id} carrera={self.carrera_id}>"
