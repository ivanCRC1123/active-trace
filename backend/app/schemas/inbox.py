"""Pydantic schemas for C-20 mensajería interna (F11.2).

PII: participantes y remitentes se exponen por nombre/apellidos (no cifrados).
NUNCA se expone email ni cuil en estos schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HiloCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asunto: str
    destinatario_ids: list[UUID]
    mensaje: str


class MensajeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cuerpo: str


class ParticipanteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    nombre: str
    apellidos: str


class MensajeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    hilo_id: UUID
    remitente_id: Optional[UUID]        # None = mensaje del sistema
    remitente_nombre: Optional[str]     # None si mensaje del sistema
    remitente_apellidos: Optional[str]  # None si mensaje del sistema
    cuerpo: str
    created_at: datetime


class HiloResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    asunto: str
    participantes: list[ParticipanteResponse]
    created_at: datetime


class HiloDetalle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    asunto: str
    participantes: list[ParticipanteResponse]
    mensajes: list[MensajeResponse]
    created_at: datetime
