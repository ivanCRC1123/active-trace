"""Pydantic schemas for C-11 analisis-atrasados-reportes endpoints."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ── Finalizacion import ────────────────────────────────────────────────────────

class FinalizacionImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actividades_detectadas: int
    entradas_procesadas: int
    finalizadas: int
    no_vinculadas: int
    sin_corregir_count: int
    warnings: list[str]


# ── Atrasados ─────────────────────────────────────────────────────────────────

class AlumnoAtrasado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None = None
    regional: str | None = None
    actividades_faltantes: list[str]
    actividades_bajo_umbral: list[str]


class AtrasadosResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_alumnos: int
    total_atrasados: int
    atrasados: list[AlumnoAtrasado]


# ── Ranking ───────────────────────────────────────────────────────────────────

class RankingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    posicion: int
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None = None
    total_aprobadas: int
    total_calificaciones: int


class RankingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RankingItem]
    total_incluidos: int
    total_excluidos: int


# ── Reporte rápido ────────────────────────────────────────────────────────────

class ReporteRapidoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total_alumnos: int
    total_actividades: int
    total_aprobaciones: int
    total_desaprobaciones: int
    alumnos_con_desaprobacion: int
    alumnos_atrasados: int
    tiene_datos: bool


# ── Notas finales ─────────────────────────────────────────────────────────────

class NotaFinalAlumno(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None = None
    aprobadas: int
    total_calificaciones: int
    pct_actividades_aprobadas: float | None = None  # None if no calificaciones


class NotasFinalesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[NotaFinalAlumno]
    total_alumnos: int


# ── Sin corregir ──────────────────────────────────────────────────────────────

class EntregaSinCorregir(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None = None
    actividad: str


class SinCorregirResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[EntregaSinCorregir]
    total: int
    aviso: str | None = None  # "no_hay_finalizacion_importada" when empty


# ── Monitor ───────────────────────────────────────────────────────────────────

class MonitorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None = None
    regional: str | None = None
    materia_id: UUID
    cohorte_id: UUID
    estado: str  # "atrasado" | "al_dia"
    actividades_faltantes: list[str]
    actividades_bajo_umbral: list[str]
    total_aprobadas: int
    total_calificaciones: int


class MonitorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MonitorItem]
    total: int
    limit: int
    offset: int
