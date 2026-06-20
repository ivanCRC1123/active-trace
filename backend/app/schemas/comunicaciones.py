"""Schemas Pydantic para C-12 comunicaciones-cola-worker.

Reglas:
- Nunca serializar `destinatario` (email cifrado del alumno) — solo nombre/apellidos.
- extra='forbid' en todos los schemas de request.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Requests ──────────────────────────────────────────────────────────────────


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID
    cohorte_id: UUID
    asunto_template: str = Field(min_length=1, max_length=500)
    cuerpo_template: str = Field(min_length=1)
    destinatarios: list[UUID] = Field(min_length=1)


class CrearLoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID
    cohorte_id: UUID
    asunto_template: str = Field(min_length=1, max_length=500)
    cuerpo_template: str = Field(min_length=1)
    destinatarios: list[UUID] = Field(min_length=1)


# ── Response items ────────────────────────────────────────────────────────────


class PreviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    asunto_renderizado: str
    cuerpo_renderizado: str


class PreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PreviewItem]
    total: int


class LoteCreado(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lote_id: UUID
    total_encolados: int
    requiere_aprobacion: bool


class ComunicacionItem(BaseModel):
    """Item para listados — sin PII (sin campo destinatario)."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    entrada_padron_id: UUID | None
    nombre: str | None
    apellidos: str | None
    estado: str
    enviado_at: datetime | None
    aprobado_at: datetime | None


class ResumenEstados(BaseModel):
    model_config = ConfigDict(extra="forbid")

    PENDIENTE: int = 0
    ENVIANDO: int = 0
    ENVIADO: int = 0
    ERROR: int = 0
    CANCELADO: int = 0


class LoteDetalle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lote_id: UUID
    materia_id: UUID
    enviado_por: UUID
    resumen_estados: ResumenEstados
    items: list[ComunicacionItem]


class AprobacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lote_id: UUID
    aprobadas: int
    ignoradas: int


class CancelacionLoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lote_id: UUID
    canceladas: int


class CancelacionIndividualResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    estado_previo: str
    estado_nuevo: str


class ComunicacionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ComunicacionItem]
    total: int
    limit: int
    offset: int
