"""Comunicaciones endpoints — C-12 comunicaciones-cola-worker.

Permissions:
  comunicacion:enviar   — preview, crear lote, listado, cancelar propio
  comunicacion:aprobar  — aprobar lote, cancelar cualquier lote/individual del tenant

Prefix: /api/v1/comunicaciones
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.comunicaciones import (
    AprobacionResponse,
    CancelacionIndividualResponse,
    CancelacionLoteResponse,
    CrearLoteRequest,
    ComunicacionListResponse,
    LoteCreado,
    LoteDetalle,
    PreviewRequest,
    PreviewResponse,
)
from app.services.comunicacion_service import ComunicacionService

router = APIRouter(prefix="/api/v1/comunicaciones", tags=["comunicaciones"])

_PERM_ENVIAR = require_permission("comunicacion:enviar", scoped=True)
_PERM_APROBAR = require_permission("comunicacion:aprobar", scoped=True)


def _svc(db: AsyncSession) -> ComunicacionService:
    return ComunicacionService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    status_map = {
        "comunicacion_not_found": status.HTTP_404_NOT_FOUND,
        "lote_not_found": status.HTTP_404_NOT_FOUND,
        "materia_not_found": status.HTTP_404_NOT_FOUND,
        "tenant_not_found": status.HTTP_404_NOT_FOUND,
        "sin_destinatarios_validos": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "transicion_invalida": status.HTTP_409_CONFLICT,
    }
    code = next((v for k, v in status_map.items() if msg.startswith(k)), status.HTTP_400_BAD_REQUEST)
    return HTTPException(status_code=code, detail=msg)


# ── F3.1 — Preview (RN-16, obligatorio antes de encolar) ────────────────────


@router.post(
    "/preview",
    response_model=PreviewResponse,
    summary="Preview de mensajes antes de encolar (RN-16)",
)
async def preview(
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_ENVIAR),
) -> PreviewResponse:
    current_user, _ = perm
    try:
        return await _svc(db).preview(
            materia_id=body.materia_id,
            cohorte_id=body.cohorte_id,
            asunto_template=body.asunto_template,
            cuerpo_template=body.cuerpo_template,
            destinatarios=body.destinatarios,
            current_user=current_user,
        )
    except ValueError as exc:
        raise _http(exc)


# ── F3.2 — Crear lote ────────────────────────────────────────────────────────


@router.post(
    "/lotes",
    response_model=LoteCreado,
    status_code=status.HTTP_201_CREATED,
    summary="Encolar comunicaciones masivas (F3.2)",
)
async def crear_lote(
    body: CrearLoteRequest,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_ENVIAR),
) -> LoteCreado:
    current_user, scope = perm
    try:
        return await _svc(db).crear_lote(
            materia_id=body.materia_id,
            cohorte_id=body.cohorte_id,
            asunto_template=body.asunto_template,
            cuerpo_template=body.cuerpo_template,
            destinatarios=body.destinatarios,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)


# ── Detalle de lote ───────────────────────────────────────────────────────────


@router.get(
    "/lotes/{lote_id}",
    response_model=LoteDetalle,
    summary="Detalle y estado de un lote de comunicaciones",
)
async def get_lote(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_ENVIAR),
) -> LoteDetalle:
    current_user, _ = perm
    try:
        return await _svc(db).get_lote(lote_id=lote_id, current_user=current_user)
    except ValueError as exc:
        raise _http(exc)


# ── F3.3 — Aprobar lote (FL-04 Parte B) ─────────────────────────────────────


@router.post(
    "/lotes/{lote_id}/aprobar",
    response_model=AprobacionResponse,
    summary="Aprobar lote pendiente (RN-17, comunicacion:aprobar)",
)
async def aprobar_lote(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_APROBAR),
) -> AprobacionResponse:
    current_user, _ = perm
    try:
        return await _svc(db).aprobar_lote(lote_id=lote_id, current_user=current_user)
    except ValueError as exc:
        raise _http(exc)


# ── Cancelar lote ─────────────────────────────────────────────────────────────


@router.post(
    "/lotes/{lote_id}/cancelar",
    response_model=CancelacionLoteResponse,
    summary="Cancelar todos los PENDIENTE de un lote",
)
async def cancelar_lote(
    lote_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_APROBAR),
) -> CancelacionLoteResponse:
    current_user, _ = perm
    try:
        return await _svc(db).cancelar_lote(lote_id=lote_id, current_user=current_user)
    except ValueError as exc:
        raise _http(exc)


# ── Cancelar individual ───────────────────────────────────────────────────────


@router.post(
    "/{com_id}/cancelar",
    response_model=CancelacionIndividualResponse,
    summary="Cancelar una comunicación individual (FL-04 Parte B)",
)
async def cancelar_individual(
    com_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_APROBAR),
) -> CancelacionIndividualResponse:
    current_user, _ = perm
    try:
        return await _svc(db).cancelar_individual(
            com_id=com_id, current_user=current_user
        )
    except ValueError as exc:
        raise _http(exc)


# ── Listado con filtros ───────────────────────────────────────────────────────


@router.get(
    "",
    response_model=ComunicacionListResponse,
    summary="Listado de comunicaciones (con filtros opcionales)",
)
async def list_comunicaciones(
    lote_id: UUID | None = Query(None),
    estado: str | None = Query(None, description="PENDIENTE|ENVIANDO|ENVIADO|ERROR|CANCELADO"),
    materia_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_ENVIAR),
) -> ComunicacionListResponse:
    current_user, scope = perm
    try:
        return await _svc(db).list_comunicaciones(
            current_user=current_user,
            scope=scope,
            lote_id=lote_id,
            estado=estado,
            materia_id=materia_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise _http(exc)
