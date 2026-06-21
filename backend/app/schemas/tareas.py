"""Schemas Pydantic para C-16 tareas-internas (E12)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UsuarioResumen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    nombre: str
    apellidos: str


class TareaCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asignado_a: UUID
    descripcion: str = Field(min_length=1, max_length=2000)
    materia_id: UUID | None = None
    contexto_id: UUID | None = None


class TareaEstadoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"]


class ComentarioCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(min_length=1, max_length=4000)


class TareaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    materia_id: UUID | None
    asignado_a: UsuarioResumen
    asignado_por: UsuarioResumen
    estado: str
    descripcion: str
    contexto_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ComentarioResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tarea_id: UUID
    autor: UsuarioResumen
    texto: str
    creado_at: datetime


class MisTareasFiltros(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"] | None = None
    materia_id: UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class TareaFiltros(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asignado_a: UUID | None = None
    asignado_por: UUID | None = None
    materia_id: UUID | None = None
    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"] | None = None
    q: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
