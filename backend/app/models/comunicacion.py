"""Comunicacion model — E21 (C-12 comunicaciones-cola-worker).

Estado FSM (RN-15):
  PENDIENTE → ENVIANDO → ENVIADO
  PENDIENTE → CANCELADO
  ENVIANDO  → ERROR
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin, EncryptedString


class EstadoComunicacion(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    ENVIANDO = "ENVIANDO"
    ENVIADO = "ENVIADO"
    ERROR = "ERROR"
    CANCELADO = "CANCELADO"


# Transiciones válidas de la FSM (RN-15)
TRANSICIONES_VALIDAS: dict[EstadoComunicacion, set[EstadoComunicacion]] = {
    EstadoComunicacion.PENDIENTE: {
        EstadoComunicacion.ENVIANDO,
        EstadoComunicacion.CANCELADO,
    },
    EstadoComunicacion.ENVIANDO: {
        EstadoComunicacion.ENVIADO,
        EstadoComunicacion.ERROR,
    },
}


def validar_transicion(actual: str, nuevo: str) -> None:
    """Levanta ValueError si la transición no está permitida por la FSM."""
    try:
        actual_e = EstadoComunicacion(actual)
        nuevo_e = EstadoComunicacion(nuevo)
    except ValueError:
        raise ValueError(f"estado_invalido: {actual!r} → {nuevo!r}")
    permitidos = TRANSICIONES_VALIDAS.get(actual_e, set())
    if nuevo_e not in permitidos:
        raise ValueError(
            f"transicion_invalida: {actual_e.value} → {nuevo_e.value}. "
            f"Permitidos desde {actual_e.value}: "
            f"{[e.value for e in permitidos]}"
        )


class Comunicacion(Base, BaseEntityMixin):
    """Registro de un email saliente a un alumno (E21)."""

    __tablename__ = "comunicacion"

    enviado_por: Mapped[UUID] = mapped_column(
        ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    materia_id: Mapped[UUID] = mapped_column(
        ForeignKey("materia.id", ondelete="RESTRICT"), nullable=False
    )
    entrada_padron_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("entrada_padron.id", ondelete="SET NULL"), nullable=True
    )
    # email del alumno; cifrado AES-256 en reposo (EncryptedString)
    destinatario: Mapped[str] = mapped_column(EncryptedString(500), nullable=False)
    asunto: Mapped[str] = mapped_column(String(500), nullable=False)
    cuerpo: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EstadoComunicacion.PENDIENTE.value
    )
    lote_id: Mapped[UUID] = mapped_column(nullable=False)
    aprobado_por: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    aprobado_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    enviado_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Comunicacion id={self.id} estado={self.estado} lote={self.lote_id}>"
