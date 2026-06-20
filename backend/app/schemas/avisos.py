"""Pydantic schemas for C-15 avisos-y-acknowledgment."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.aviso import AlcanceAviso, SeveridadAviso

# Closed catalog of valid roles — enforced at schema level (concern #2 / rol_destino)
_ROL_VALIDO = Literal[
    "ALUMNO", "TUTOR", "PROFESOR", "COORDINADOR", "NEXO", "ADMIN", "FINANZAS"
]


class AvisoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alcance: AlcanceAviso
    materia_id: UUID | None = None
    cohorte_id: UUID | None = None
    rol_destino: _ROL_VALIDO | None = None  # closed catalog; only allowed for PorRol
    severidad: SeveridadAviso
    titulo: str = Field(min_length=1, max_length=255)
    cuerpo: str = Field(min_length=1)
    inicio_en: datetime
    fin_en: datetime
    orden: int = Field(default=0, ge=0)
    activo: bool = True
    requiere_ack: bool = False

    @model_validator(mode="after")
    def validar_scope_y_vigencia(self) -> "AvisoCreate":
        a = self.alcance

        # Scope consistency (concern #2 — also raises 422 at request level)
        if a == AlcanceAviso.PorMateria and self.materia_id is None:
            raise ValueError("materia_id required for alcance PorMateria")
        if a == AlcanceAviso.PorCohorte and self.cohorte_id is None:
            raise ValueError("cohorte_id required for alcance PorCohorte")
        if a == AlcanceAviso.PorRol and self.rol_destino is None:
            raise ValueError("rol_destino required for alcance PorRol")
        if a != AlcanceAviso.PorMateria and self.materia_id is not None:
            raise ValueError("materia_id only allowed for alcance PorMateria")
        if a != AlcanceAviso.PorCohorte and self.cohorte_id is not None:
            raise ValueError("cohorte_id only allowed for alcance PorCohorte")
        if a != AlcanceAviso.PorRol and self.rol_destino is not None:
            raise ValueError("rol_destino only allowed for alcance PorRol")

        # Vigencia sanity check (concern #1 / RN-18 — raised before DB hit)
        if self.fin_en <= self.inicio_en:
            raise ValueError("fin_en must be after inicio_en")

        return self


class AvisoUpdate(BaseModel):
    """Only content-level fields are mutable; scope fields (alcance, *_id, rol_destino)
    cannot be changed after creation — changing audience of a published aviso is confusing."""

    model_config = ConfigDict(extra="forbid")

    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    cuerpo: str | None = None
    severidad: SeveridadAviso | None = None
    inicio_en: datetime | None = None
    fin_en: datetime | None = None
    orden: int | None = Field(default=None, ge=0)
    activo: bool | None = None
    requiere_ack: bool | None = None

    @model_validator(mode="after")
    def validar_vigencia_si_ambas(self) -> "AvisoUpdate":
        if self.inicio_en is not None and self.fin_en is not None:
            if self.fin_en <= self.inicio_en:
                raise ValueError("fin_en must be after inicio_en")
        return self


class AvisoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    alcance: AlcanceAviso
    materia_id: UUID | None
    cohorte_id: UUID | None
    rol_destino: str | None
    severidad: SeveridadAviso
    titulo: str
    cuerpo: str
    inicio_en: datetime
    fin_en: datetime
    orden: int
    activo: bool
    requiere_ack: bool
    created_at: datetime
    updated_at: datetime


class AvisoStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aviso_id: UUID
    confirmaciones: int  # = "vistas" per design decision D9; no separate view tracking


class AckAvisoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    aviso_id: UUID
    usuario_id: UUID
    created_at: datetime  # = confirmado_at per KB E13
