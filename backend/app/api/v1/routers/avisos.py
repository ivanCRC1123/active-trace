"""Router for C-15 avisos-y-acknowledgment."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.avisos import AckAvisoResponse, AvisoCreate, AvisoResponse, AvisoStats, AvisoUpdate
from app.services.avisos_service import AvisosService

router = APIRouter(prefix="/api/v1/avisos", tags=["avisos"])

_PERM_PUBLICAR = require_permission("avisos:publicar")
_PERM_ACK      = require_permission("comunicacion:confirmar_aviso")


def _svc(db: AsyncSession) -> AvisosService:
    return AvisosService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


# ── Endpoints de consumo (BEFORE /{id} to avoid path collision) ─────────

@router.get("/mis-avisos", response_model=list[AvisoResponse])
async def mis_avisos(
    auth=Depends(_PERM_ACK),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    now = datetime.now(timezone.utc)
    return await _svc(db).mis_avisos(
        tenant_id=current_user.tenant_id,
        current_user=current_user,
        now=now,
    )


# ── Endpoints de gestión (avisos:publicar) ─────────────────────────────

@router.get("/", response_model=list[AvisoResponse])
async def list_avisos(
    auth=Depends(_PERM_PUBLICAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_avisos(tenant_id=current_user.tenant_id)


@router.post("/", response_model=AvisoResponse, status_code=status.HTTP_201_CREATED)
async def create_aviso(
    body: AvisoCreate,
    auth=Depends(_PERM_PUBLICAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).create_aviso(
            tenant_id=current_user.tenant_id,
            data=body,
            current_user=current_user,
        )
    except ValueError as exc:
        raise _http(exc)


@router.get("/{id}", response_model=AvisoResponse)
async def get_aviso(
    id: UUID,
    auth=Depends(_PERM_PUBLICAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_aviso(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router.patch("/{id}", response_model=AvisoResponse)
async def update_aviso(
    id: UUID,
    body: AvisoUpdate,
    auth=Depends(_PERM_PUBLICAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).update_aviso(
            id=id, tenant_id=current_user.tenant_id, data=body
        )
    except ValueError as exc:
        raise _http(exc)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_aviso(
    id: UUID,
    auth=Depends(_PERM_PUBLICAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).delete_aviso(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router.get("/{id}/stats", response_model=AvisoStats)
async def stats_aviso(
    id: UUID,
    auth=Depends(_PERM_PUBLICAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).stats_aviso(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router.post("/{id}/ack", response_model=AckAvisoResponse)
async def confirmar_aviso(
    id: UUID,
    response: Response,
    auth=Depends(_PERM_ACK),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        ack, created = await _svc(db).confirmar_aviso(
            tenant_id=current_user.tenant_id,
            aviso_id=id,
            current_user=current_user,
        )
        response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return AckAvisoResponse.model_validate(ack)
    except ValueError as exc:
        raise _http(exc)
