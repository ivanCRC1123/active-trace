"""Guardia model — C-13 épica 6 E11 + D-C13-6.

D-C13-6: campo `fecha DATE nullable` es extensión de E11 (no está en la KB).
Permite distinguir guardias de semanas distintas y consultas por rango de fechas.
"""

from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class Guardia(Base, BaseEntityMixin):
    __tablename__ = "guardia"

    asignacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    carrera_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("carrera.id", ondelete="RESTRICT"), nullable=True
    )
    cohorte_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("cohorte.id", ondelete="RESTRICT"), nullable=True
    )
    dia: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # D-C13-6
    horario: Mapped[str] = mapped_column(String(50), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'Pendiente'"), default="Pendiente"
    )
    comentarios: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
