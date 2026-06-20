"""Pydantic schemas for Carrera (E1), Cohorte (E2) and Materia (E3)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.base import EstadoBasico

# ── Carrera ────────────────────────────────────────────────────────────────


class CarreraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    nombre: str


class CarreraUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = None
    nombre: str | None = None
    estado: EstadoBasico | None = None


class CarreraResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    codigo: str
    nombre: str
    estado: EstadoBasico
    created_at: datetime
    updated_at: datetime


# ── Cohorte ────────────────────────────────────────────────────────────────


class CohorteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carrera_id: UUID
    nombre: str
    anio: int
    vig_desde: date
    vig_hasta: date | None = None


class CohorteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = None
    anio: int | None = None
    vig_desde: date | None = None
    vig_hasta: date | None = None
    estado: EstadoBasico | None = None


class CohorteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    carrera_id: UUID
    nombre: str
    anio: int
    vig_desde: date
    vig_hasta: date | None
    estado: EstadoBasico
    created_at: datetime
    updated_at: datetime


# ── Materia ────────────────────────────────────────────────────────────────


class MateriaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    nombre: str


class MateriaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str | None = None
    nombre: str | None = None
    estado: EstadoBasico | None = None


class MateriaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    codigo: str
    nombre: str
    estado: EstadoBasico
    created_at: datetime
    updated_at: datetime
