"""Facturas endpoints (C-18 — F10.5).

ABM de facturas de docentes con facturador=True + transición Pendiente↔Abonada.
Todos los endpoints requieren ``facturas:gestionar`` (FINANZAS-only).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.models.base import FacturaEstado
from app.schemas.facturas import (
    FacturaCambiarEstadoRequest,
    FacturaCreate,
    FacturaResponse,
    FacturaUpdate,
)
from app.services.factura_service import FacturaService

router_facturas = APIRouter(prefix="/api/v1/facturas", tags=["facturas"])

_PERM = require_permission("facturas:gestionar")


def _svc(db: AsyncSession) -> FacturaService:
    return FacturaService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "no es facturador" in msg:
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router_facturas.post("/", response_model=FacturaResponse, status_code=status.HTTP_201_CREATED)
async def crear_factura(
    body: FacturaCreate,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).crear(current_user=current_user, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_facturas.get("/", response_model=list[FacturaResponse])
async def listar_facturas(
    usuario_id: UUID | None = None,
    estado: FacturaEstado | None = None,
    periodo: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    q: str | None = None,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).listar(
        tenant_id=current_user.tenant_id,
        usuario_id=usuario_id,
        estado=estado,
        periodo=periodo,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        q=q,
    )


@router_facturas.get("/{id}", response_model=FacturaResponse)
async def get_factura(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router_facturas.put("/{id}", response_model=FacturaResponse)
async def editar_factura(
    id: UUID,
    body: FacturaUpdate,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).editar(current_user=current_user, id=id, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_facturas.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def baja_factura(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).baja(current_user=current_user, id=id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        raise _http(exc)


@router_facturas.post("/{id}/estado", response_model=FacturaResponse)
async def cambiar_estado_factura(
    id: UUID,
    body: FacturaCambiarEstadoRequest,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).cambiar_estado(current_user=current_user, id=id, data=body)
    except ValueError as exc:
        raise _http(exc)
