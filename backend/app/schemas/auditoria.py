"""Pydantic v2 schemas for audit log and impersonation endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
