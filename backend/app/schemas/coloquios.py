"""Pydantic schemas for C-14 evaluaciones-y-coloquios."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import TipoEvaluacion
from app.models.evaluacion import EstadoReserva


class EvaluacionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID
    cohorte_id: UUID
    tipo: TipoEvaluacion
    instancia: str = Field(min_length=1, max_length=255)
    dias_disponibles: int = Field(ge=1)
    cupo_total: int = Field(ge=0, description="0 = sin límite de cupos")


class EvaluacionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instancia: str | None = Field(default=None, min_length=1, max_length=255)
    dias_disponibles: int | None = Field(default=None, ge=1)
    cupo_total: int | None = Field(default=None, ge=0)


class EvaluacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    cohorte_id: UUID
    tipo: TipoEvaluacion
    instancia: str
    dias_disponibles: int
    cupo_total: int
    created_at: datetime
    updated_at: datetime


class MetricasConvocatoria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluacion_id: UUID
    convocados: int
    reservas_activas: int
    cupos_libres: int
    notas_registradas: int


class MetricasPanel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_alumnos_cargados: int
    instancias_activas: int
    reservas_activas: int
    notas_registradas: int


class ConvocadoImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    email: str = Field(min_length=1)
    usuario_id: UUID | None = None


class ConvocadoImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filas: list[ConvocadoImportRow] = Field(min_length=1)


class ConvocadoImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    insertados: int


class ReservaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_hora: datetime


class ReservaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    evaluacion_id: UUID
    alumno_id: UUID
    fecha_hora: datetime
    estado: EstadoReserva
    created_at: datetime
    updated_at: datetime


class ResultadoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alumno_id: UUID
    nota_final: str = Field(min_length=1, max_length=255)


class ResultadoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    evaluacion_id: UUID
    alumno_id: UUID
    nota_final: str
    created_at: datetime
    updated_at: datetime
