"""Pydantic schemas for C-20 perfil propio (F11.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class PerfilResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    tenant_id: UUID
    nombre: str
    apellidos: str
    email: str           # plaintext (EncryptedString TypeDecorator descifra en SELECT)
    sexo: str | None
    dni: str | None
    cuil: str | None     # solo lectura — no aparece en PerfilUpdate
    cbu: str | None
    alias_cbu: str | None
    banco: str | None
    regional: str | None
    legajo: str | None          # solo lectura — asignado por ADMIN
    legajo_profesional: str | None
    facturador: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PerfilUpdate(BaseModel):
    """Campos editables por el propio usuario.

    cuil y legajo están ausentes (no editables por el usuario).
    extra='forbid' rechaza cualquier intento de enviarlos.
    """

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = None
    apellidos: str | None = None
    email: EmailStr | None = None
    sexo: str | None = None
    dni: str | None = None
    cbu: str | None = None
    alias_cbu: str | None = None
    banco: str | None = None
    regional: str | None = None
    legajo_profesional: str | None = None
    facturador: bool | None = None
