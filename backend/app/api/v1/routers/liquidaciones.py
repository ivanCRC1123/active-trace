"""Liquidaciones endpoints (C-18 — F10.2/F10.3/F10.4/F10.5/F10.6).

All endpoints require ``liquidaciones:calcular_cerrar`` (FINANZAS-only).

NOTE: F10.1/F10.3/F10.6 also list liquidaciones for ADMIN review, but
``liquidaciones:ver`` does not appear in the permission matrix. A separate
read permission is NOT invented here. FINANZAS sees everything via
``calcular_cerrar``. See design.md §OD-RBAC-GAP for the open inconsistency.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.liquidaciones import (
    CalcularLiquidacionRequest,
    CalcularLiquidacionResponse,
    CerrarLiquidacionRequest,
    CerrarLiquidacionResponse,
    KPIsLiquidacionResponse,
    LiquidacionResponse,
)
from app.services.liquidacion_service import LiquidacionService

router_liquidaciones = APIRouter(prefix="/api/v1/liquidaciones", tags=["liquidaciones"])

_PERM = require_permission("liquidaciones:calcular_cerrar")


def _svc(db: AsyncSession) -> LiquidacionService:
    return LiquidacionService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "ya cerrado" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    if "no hay liquidaciones" in msg:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router_liquidaciones.post(
    "/calcular",
    response_model=CalcularLiquidacionResponse,
    status_code=200,
)
async def calcular_liquidaciones(
    body: CalcularLiquidacionRequest,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).calcular(current_user=current_user, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_liquidaciones.post(
    "/cerrar",
    response_model=CerrarLiquidacionResponse,
    status_code=200,
)
async def cerrar_liquidaciones(
    body: CerrarLiquidacionRequest,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).cerrar(current_user=current_user, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_liquidaciones.get("/", response_model=list[LiquidacionResponse])
async def list_liquidaciones(
    cohorte_id: UUID,
    periodo: str,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_liquidaciones(
        tenant_id=current_user.tenant_id,
        cohorte_id=cohorte_id,
        periodo=periodo,
    )


@router_liquidaciones.get("/kpis", response_model=KPIsLiquidacionResponse)
async def kpis_liquidaciones(
    cohorte_id: UUID,
    periodo: str,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).get_kpis(
        tenant_id=current_user.tenant_id,
        cohorte_id=cohorte_id,
        periodo=periodo,
    )


@router_liquidaciones.get("/{id}", response_model=LiquidacionResponse)
async def get_liquidacion(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_liquidacion(
            id=id, tenant_id=current_user.tenant_id
        )
    except ValueError as exc:
        raise _http(exc)
