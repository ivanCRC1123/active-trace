"""Pydantic schemas for Factura (E20) — C-18 Section 3."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import FacturaEstado


class FacturaCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    periodo: str = Field(min_length=7, max_length=7, pattern=r"^\d{4}-\d{2}$")
    detalle: str = Field(min_length=1)
    referencia_archivo: str = Field(min_length=1)
    tamano_kb: Decimal = Field(gt=0)


class FacturaUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detalle: Optional[str] = Field(default=None, min_length=1)
    referencia_archivo: Optional[str] = Field(default=None, min_length=1)
    tamano_kb: Optional[Decimal] = Field(default=None, gt=0)


class FacturaCambiarEstadoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estado: FacturaEstado


class FacturaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    usuario_id: UUID
    periodo: str
    detalle: str
    referencia_archivo: str
    tamano_kb: Decimal
    estado: FacturaEstado
    cargada_at: datetime
    abonada_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
