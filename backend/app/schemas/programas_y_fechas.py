"""Pydantic schemas for ProgramaMateria (E16) and FechaAcademica (E15)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import TipoEvaluacion


class ProgramaMateriaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID
    carrera_id: UUID
    cohorte_id: UUID
    titulo: str = Field(min_length=1, max_length=255)
    referencia_archivo: str = Field(min_length=1)


class ProgramaMateriaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    referencia_archivo: str | None = Field(default=None, min_length=1)


class ProgramaMateriaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    carrera_id: UUID
    cohorte_id: UUID
    titulo: str
    referencia_archivo: str
    cargado_at: datetime
    created_at: datetime
    updated_at: datetime


class FechaAcademicaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID
    cohorte_id: UUID
    tipo: TipoEvaluacion
    numero: int = Field(ge=1)
    periodo: str = Field(min_length=1, max_length=20)
    fecha: date
    titulo: str = Field(min_length=1, max_length=255)


class FechaAcademicaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha: date | None = None
    titulo: str | None = Field(default=None, min_length=1, max_length=255)


class FechaAcademicaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    cohorte_id: UUID
    tipo: TipoEvaluacion
    numero: int
    periodo: str
    fecha: date
    titulo: str
    created_at: datetime
    updated_at: datetime
