"""FinalizacionActividad — LMS completion status per student × activity (C-11).

Persists the completion state reported by the LMS for each student and activity.
Used to detect "sin corregir" entries: finalizado=True but no Calificacion row (RN-07/08).

`asignacion_id` provides scope isolation identical to Calificacion (RN-04):
a PROFESOR can only clear/see their own import batch.

PII note: the email from the finalization file is used only to resolve
`entrada_padron_id` during import; it is NOT stored here.
"""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class FinalizacionActividad(Base, BaseEntityMixin):
    __tablename__ = "finalizacion_actividad"

    entrada_padron_id: Mapped[UUID] = mapped_column(
        ForeignKey("entrada_padron.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    asignacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=False
    )
    actividad: Mapped[str] = mapped_column(String(500), nullable=False)
    finalizado: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return (
            f"<FinalizacionActividad id={self.id} "
            f"entrada_padron_id={self.entrada_padron_id} "
            f"actividad={self.actividad!r} finalizado={self.finalizado}>"
        )
