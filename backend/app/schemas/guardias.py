"""Schemas C-13 guardias (F6.6)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GuardiaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asignacion_id: UUID
    materia_id: UUID
    carrera_id: Optional[UUID] = None
    cohorte_id: Optional[UUID] = None
    dia: str
    fecha: Optional[date] = None          # D-C13-6 aprobado
    horario: str
    comentarios: Optional[str] = None


class GuardiaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Optional[Literal["Pendiente", "Realizada", "Cancelada"]] = None
    comentarios: Optional[str] = None
    horario: Optional[str] = None
    fecha: Optional[date] = None


class GuardiaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    asignacion_id: UUID
    materia_id: UUID
    carrera_id: Optional[UUID]
    cohorte_id: Optional[UUID]
    dia: str
    fecha: Optional[date]
    horario: str
    estado: str
    comentarios: Optional[str]
    created_at: datetime
    updated_at: datetime
