"""SlotEncuentro model — C-13 épica 6 E9."""

from datetime import date, time
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Time, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class SlotEncuentro(Base, BaseEntityMixin):
    __tablename__ = "slot_encuentro"

    asignacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    hora: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    dia_semana: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    fecha_inicio: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    cant_semanas: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    fecha_unica: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    meet_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vig_desde: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    vig_hasta: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
