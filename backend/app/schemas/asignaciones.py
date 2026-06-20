"""Pydantic schemas for Asignacion (C-07)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AsignacionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    rol_id: UUID
    materia_id: UUID | None = None
    carrera_id: UUID | None = None
    cohorte_id: UUID | None = None
    responsable_id: UUID | None = None
    comisiones: list = []
    desde: date
    hasta: date | None = None


class AsignacionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comisiones: list | None = None
    responsable_id: UUID | None = None
    hasta: date | None = None


class AsignacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    usuario_id: UUID
    rol_id: UUID
    materia_id: UUID | None = None
    carrera_id: UUID | None = None
    cohorte_id: UUID | None = None
    responsable_id: UUID | None = None
    comisiones: list
    desde: date
    hasta: date | None = None
    estado_vigencia: str
    created_at: datetime
    updated_at: datetime
