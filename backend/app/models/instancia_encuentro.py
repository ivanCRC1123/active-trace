"""InstanciaEncuentro model — C-13 épica 6 E10.

Estado independiente del slot (RN-14). asignacion_id siempre poblado
(denormalizado de slot) para scoping eficiente del PROFESOR(own).
"""

from datetime import date, time
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, String, Text, Time, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin


class InstanciaEncuentro(Base, BaseEntityMixin):
    __tablename__ = "instancia_encuentro"

    slot_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("slot_encuentro.id", ondelete="SET NULL"), nullable=True
    )
    # Denormalizado de slot para scoping PROFESOR(own) sin JOINs profundos.
    # En instancias derivadas de slot: slot.asignacion_id.
    # En instancias standalone (slot_id=NULL): asignacion del creador.
    asignacion_id: Mapped[UUID] = mapped_column(
        ForeignKey("asignacion.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    hora: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'Programado'"), default="Programado"
    )
    meet_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    comentario: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
