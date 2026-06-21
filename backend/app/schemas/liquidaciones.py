"""Pydantic schemas for Liquidacion (E19) — C-18 Section 2."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.base import LiquidacionEstado, RolLiquidable


# ── Request ──────────────────────────────────────────────────────────────────

class CalcularLiquidacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohorte_id: UUID
    periodo: str = Field(min_length=7, max_length=7, pattern=r"^\d{4}-\d{2}$")


class CerrarLiquidacionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cohorte_id: UUID
    periodo: str = Field(min_length=7, max_length=7, pattern=r"^\d{4}-\d{2}$")


# ── Response atoms ────────────────────────────────────────────────────────────

class LiquidacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    tenant_id: UUID
    cohorte_id: UUID
    periodo: str
    usuario_id: UUID
    rol: RolLiquidable
    comisiones: list
    monto_base: Decimal
    monto_plus: Decimal
    total: Decimal
    es_nexo: bool
    excluido_por_factura: bool
    datos_bancarios_incompletos: bool
    estado: LiquidacionEstado
    created_at: datetime
    updated_at: datetime


class DocenteIncompletoInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario_id: UUID
    rol: RolLiquidable
    motivo: str


# ── Calcular response ─────────────────────────────────────────────────────────

class CalcularLiquidacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liquidaciones: list[LiquidacionResponse]
    sin_base_vigente: list[DocenteIncompletoInfo]
    sin_datos_bancarios: list[DocenteIncompletoInfo]


# ── Cerrar response ───────────────────────────────────────────────────────────

class CerrarLiquidacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cerradas: int
    cohorte_id: UUID
    periodo: str


# ── KPIs response ─────────────────────────────────────────────────────────────

class KPIsLiquidacionResponse(BaseModel):
    """KPI summary for a (cohorte, periodo) pair.

    total_con_factura: count of Abonada facturas (E20 has no monto field — OD-7).
    total_sin_factura: Σ totals of non-facturador liquidaciones (NEXO included — RN-36).
    """
    model_config = ConfigDict(extra="forbid")

    cohorte_id: UUID
    periodo: str
    total_sin_factura: Decimal
    total_con_factura: int
    count_docentes: int
    count_abierta: int
    count_cerrada: int
