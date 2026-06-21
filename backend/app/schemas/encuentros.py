"""Schemas C-13 encuentros (F6.1–F6.5)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SlotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asignacion_id: UUID
    materia_id: UUID
    titulo: str
    hora: time
    modo: Literal["recurrente", "unico"]
    dia_semana: Optional[str] = None       # solo recurrente (Lunes..Domingo)
    fecha_inicio: Optional[date] = None    # solo recurrente — D-C13-1: debe caer en dia_semana
    cant_semanas: Optional[int] = None     # solo recurrente
    fecha_unica: Optional[date] = None     # solo único
    meet_url: Optional[str] = None
    vig_desde: Optional[date] = None
    vig_hasta: Optional[date] = None


class InstanciaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Optional[Literal["Programado", "Realizado", "Cancelado"]] = None
    meet_url: Optional[str] = None
    video_url: Optional[str] = None
    comentario: Optional[str] = None


class InstanciaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    slot_id: Optional[UUID]
    asignacion_id: UUID
    materia_id: UUID
    fecha: date
    hora: time
    titulo: str
    estado: str
    meet_url: Optional[str]
    video_url: Optional[str]
    comentario: Optional[str]
    created_at: datetime
    updated_at: datetime


class SlotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    asignacion_id: UUID
    materia_id: UUID
    titulo: str
    hora: time
    modo: str          # "recurrente" | "unico" (derivado de cant_semanas > 0)
    dia_semana: Optional[str]
    fecha_inicio: Optional[date]
    cant_semanas: int
    fecha_unica: Optional[date]
    meet_url: Optional[str]
    vig_desde: Optional[date]
    vig_hasta: Optional[date]
    created_at: datetime


class SlotConInstanciasResponse(SlotResponse):
    model_config = ConfigDict(extra="forbid")

    instancias: list[InstanciaResponse]


class FragmentoLMSResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fragmento: str
