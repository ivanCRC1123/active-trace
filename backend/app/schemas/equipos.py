"""Pydantic schemas for C-08 equipos-docentes operations."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


class EquipoFiltros(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID | None = None
    carrera_id: UUID | None = None
    cohorte_id: UUID | None = None
    usuario_id: UUID | None = None
    responsable_id: UUID | None = None
    rol: str | None = None
    estado_vigencia: Literal["Vigente", "Vencida"] | None = None
    limit: int = 100
    offset: int = 0


class MisEquiposFiltros(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID | None = None
    carrera_id: UUID | None = None
    cohorte_id: UUID | None = None
    rol: str | None = None
    estado_vigencia: Literal["Vigente", "Vencida"] | None = None


class AsignacionEquipoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    usuario_id: UUID
    usuario_nombre: str
    usuario_apellidos: str
    rol_id: UUID
    rol: str
    materia_id: UUID | None = None
    materia_nombre: str | None = None
    carrera_id: UUID | None = None
    carrera_nombre: str | None = None
    cohorte_id: UUID | None = None
    cohorte_nombre: str | None = None
    comisiones: list
    responsable_id: UUID | None = None
    desde: date
    hasta: date | None = None
    estado_vigencia: str


class AsignacionMasivaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_ids: list[UUID]
    rol_id: UUID
    materia_id: UUID | None = None
    carrera_id: UUID | None = None
    cohorte_id: UUID | None = None
    comisiones: list[str] = []
    responsable_id: UUID | None = None
    desde: date
    hasta: date | None = None

    @model_validator(mode="after")
    def hasta_gte_desde(self) -> "AsignacionMasivaRequest":
        if self.hasta is not None and self.hasta < self.desde:
            raise ValueError("hasta debe ser >= desde")
        if not self.usuario_ids:
            raise ValueError("usuario_ids no puede estar vacío")
        return self


class MasivaResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creados: int
    asignaciones: list[UUID]


class ContextoEquipo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID | None = None
    carrera_id: UUID | None = None
    cohorte_id: UUID | None = None

    @model_validator(mode="after")
    def al_menos_un_contexto(self) -> "ContextoEquipo":
        if self.materia_id is None and self.carrera_id is None and self.cohorte_id is None:
            raise ValueError("al menos un campo de contexto debe ser no-null")
        return self


class ClonarEquipoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origen: ContextoEquipo
    destino: ContextoEquipo
    desde: date
    hasta: date | None = None

    @model_validator(mode="after")
    def validar_fechas_y_destino(self) -> "ClonarEquipoRequest":
        if self.hasta is not None and self.hasta < self.desde:
            raise ValueError("hasta debe ser >= desde")
        if (
            self.origen.materia_id == self.destino.materia_id
            and self.origen.carrera_id == self.destino.carrera_id
            and self.origen.cohorte_id == self.destino.cohorte_id
        ):
            raise ValueError("origen y destino no pueden ser el mismo contexto")
        return self


class ClonarOmitido(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    motivo: str


class ClonarResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    creados: int
    omitidos: list[ClonarOmitido]


class VigenciaBloqueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID | None = None
    carrera_id: UUID | None = None
    cohorte_id: UUID | None = None
    desde: date
    hasta: date | None = None

    @model_validator(mode="after")
    def validar(self) -> "VigenciaBloqueRequest":
        if self.materia_id is None and self.carrera_id is None and self.cohorte_id is None:
            raise ValueError("al menos un campo de contexto debe ser no-null")
        if self.hasta is not None and self.hasta < self.desde:
            raise ValueError("hasta debe ser >= desde")
        return self


class VigenciaBloqueResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filas_afectadas: int
