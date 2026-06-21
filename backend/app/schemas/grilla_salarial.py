"""Pydantic schemas for grilla salarial: MateriaGrupo (E16a), SalarioBase (E17), SalarioPlus (E18)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import RolLiquidable


# ── MateriaGrupo ────────────────────────────────────────────────────────────

class MateriaGrupoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materia_id: UUID
    grupo: str = Field(min_length=1, max_length=50)


class MateriaGrupoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    materia_id: UUID
    grupo: str
    created_at: datetime
    updated_at: datetime


# ── SalarioBase ─────────────────────────────────────────────────────────────

class SalarioBaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rol: RolLiquidable
    monto: Decimal = Field(gt=0, decimal_places=2)
    desde: date
    hasta: Optional[date] = None


class SalarioBaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monto: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    desde: Optional[date] = None
    hasta: Optional[date] = None


class SalarioBaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    rol: RolLiquidable
    monto: Decimal
    desde: date
    hasta: Optional[date]
    created_at: datetime
    updated_at: datetime


# ── SalarioPlus ─────────────────────────────────────────────────────────────

class SalarioPlusCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grupo: str = Field(min_length=1, max_length=50)
    rol: RolLiquidable
    descripcion: str = Field(min_length=1, max_length=255)
    monto: Decimal = Field(gt=0, decimal_places=2)
    desde: date
    hasta: Optional[date] = None


class SalarioPlusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descripcion: Optional[str] = Field(default=None, min_length=1, max_length=255)
    monto: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    desde: Optional[date] = None
    hasta: Optional[date] = None


class SalarioPlusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    grupo: str
    rol: RolLiquidable
    descripcion: str
    monto: Decimal
    desde: date
    hasta: Optional[date]
    created_at: datetime
    updated_at: datetime
