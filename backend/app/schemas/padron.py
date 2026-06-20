"""Pydantic schemas for C-09 padrón ingesta."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VersionPadronResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    cohorte_id: UUID
    cargado_por: UUID
    cargado_at: datetime
    activa: bool
    total_entradas: int
    entradas_vinculadas: int
    created_at: datetime
    updated_at: datetime


class EntradaPadronResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    version_id: UUID
    tenant_id: UUID
    usuario_id: UUID | None
    nombre: str
    apellidos: str
    email: str          # plaintext — decrypted by EncryptedString TypeDecorator on read
    comision: str | None
    regional: str | None
    vinculado: bool     # True if usuario_id is not None
    created_at: datetime
    updated_at: datetime


class PadronConEntradas(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionPadronResponse
    entradas: list[EntradaPadronResponse]


class PadronImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: VersionPadronResponse
    total_importadas: int
    entradas_vinculadas: int
    advertencias: list[str]


class PadronPreviewEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str
    apellidos: str
    comision: str | None
    regional: str | None
    vinculado: bool     # True if email matches an existing User in the tenant


class PadronPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    vinculados: int
    advertencias: list[str]
    entradas: list[PadronPreviewEntry]
