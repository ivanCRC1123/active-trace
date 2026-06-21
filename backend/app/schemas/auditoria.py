"""Pydantic v2 schemas for audit log and impersonation endpoints."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImpersonateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_user_id: UUID


class ImpersonateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    impersonado_id: UUID


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    fecha_hora: datetime
    actor_id: UUID
    impersonado_id: UUID | None
    materia_id: UUID | None
    accion: str
    detalle: dict | None
    filas_afectadas: int
    ip: str | None
    user_agent: str | None


class AuditLogListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


# ── C-19 panel schemas ────────────────────────────────────────────────────────


class AccionXDia(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fecha: date
    cantidad: int


class AccionesXDiaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AccionXDia]
    total_acciones: int


class EstadoComunicacionXDocente(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: UUID
    nombre: str | None
    apellidos: str | None
    estados: dict[str, int]
    total: int


class ComunicacionesDocenteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[EstadoComunicacionXDocente]


class InteraccionXDocenteMateria(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor_id: UUID
    nombre: str | None
    apellidos: str | None
    materia_id: UUID | None
    accion: str
    cantidad: int


class InteraccionesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InteraccionXDocenteMateria]


class AuditLogPublicEntry(BaseModel):
    """scope=own (COORDINADOR): sin campos de seguridad (detalle, ip, user_agent)."""
    model_config = ConfigDict(extra="forbid")
    id: UUID
    fecha_hora: datetime
    actor_id: UUID
    nombre_actor: str | None
    apellidos_actor: str | None
    impersonado_id: UUID | None
    materia_id: UUID | None
    accion: str
    filas_afectadas: int


class AuditLogFullEntry(BaseModel):
    """scope=all (ADMIN / FINANZAS): todos los campos."""
    model_config = ConfigDict(extra="forbid")
    id: UUID
    fecha_hora: datetime
    actor_id: UUID
    nombre_actor: str | None
    apellidos_actor: str | None
    impersonado_id: UUID | None
    materia_id: UUID | None
    accion: str
    detalle: dict | None
    filas_afectadas: int
    ip: str | None
    user_agent: str | None


class UltimasAccionesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AuditLogPublicEntry | AuditLogFullEntry]
    limit_aplicado: int


class PaginatedAuditLogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[AuditLogPublicEntry | AuditLogFullEntry]
    total: int
    page: int
    page_size: int
    pages: int
