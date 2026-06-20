"""Pydantic schemas for calificaciones and umbral (C-10)."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityInfoSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str
    tipo: str  # "numerica" | "textual"


class GradePreview(BaseModel):
    """Preview of a parsed LMS grade file — no DB write."""

    model_config = ConfigDict(extra="forbid")

    actividades: list[ActivityInfoSchema]
    total_alumnos: int
    warnings: list[str]


class ImportarCalificacionesRequest(BaseModel):
    """Body for the confirm-import endpoint."""

    model_config = ConfigDict(extra="forbid")

    actividades_seleccionadas: list[str] = Field(
        min_length=1, description="Names of activities to import from the file"
    )


class CalificacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    asignacion_id: UUID
    entrada_padron_id: UUID
    materia_id: UUID
    actividad: str
    nota_numerica: Optional[Decimal]
    nota_textual: Optional[str]
    aprobado: bool
    origen: str


class ImportarCalificacionesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    importadas: int
    actualizadas: int
    omitidas: int
    warnings: list[str]


class UmbralMateriaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Optional[UUID] = None
    asignacion_id: Optional[UUID] = None
    materia_id: Optional[UUID] = None
    umbral_pct: int
    valores_aprobatorios: list[str]
    es_default: bool = False


class UmbralMateriaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    umbral_pct: int = Field(ge=0, le=100, default=60)
    valores_aprobatorios: list[str] = Field(
        default=["Satisfactorio", "Supera lo esperado"]
    )


class VaciarResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eliminadas: int
