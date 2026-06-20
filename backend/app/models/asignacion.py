"""Asignacion model — vínculo docente–contexto académico con vigencia (C-07)."""

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, JSON, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class Asignacion(Base, BaseEntityMixin):
    __tablename__ = "asignacion"

    usuario_id: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    rol_id: Mapped[UUID] = mapped_column(
        ForeignKey("rol.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=True
    )
    carrera_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("carrera.id", ondelete="RESTRICT"), nullable=True
    )
    cohorte_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"), nullable=True
    )
    responsable_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    comisiones: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default=text("'[]'::json"), default=list
    )
    desde: Mapped[date] = mapped_column(Date, nullable=False)
    hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<Asignacion id={self.id} usuario_id={self.usuario_id}>"
