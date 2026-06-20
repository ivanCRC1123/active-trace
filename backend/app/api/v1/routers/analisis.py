"""Analisis endpoints — atrasados, ranking, notas finales, sin-corregir, monitor (C-11).

Permissions:
  calificaciones:importar       — importar finalizacion (F1.2)
  atrasados:ver                 — atrasados, ranking, reporte-rapido, notas-finales, monitor
  entregas:detectar_sin_corregir — sin-corregir

Prefix: /api/v1/analisis
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.analisis import (
    AtrasadosResponse,
    FinalizacionImportResult,
    MonitorResponse,
    NotasFinalesResponse,
    RankingResponse,
    ReporteRapidoResponse,
    SinCorregirResponse,
)
from app.schemas.auth import CurrentUser
from app.services.analisis_service import AnalisisService

router = APIRouter(prefix="/api/v1/analisis", tags=["analisis"])

_PERM_IMPORTAR = require_permission("calificaciones:importar", scoped=True)
_PERM_VER = require_permission("atrasados:ver", scoped=True)
_PERM_SIN_CORREGIR = require_permission("entregas:detectar_sin_corregir", scoped=True)


def _svc(db: AsyncSession) -> AnalisisService:
    return AnalisisService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg in ("asignacion_not_found", "materia_not_found", "no_hay_padron_activo"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ── F1.2 — importar finalizacion ─────────────────────────────────────────────


@router.post(
    "/{materia_id}/cohortes/{cohorte_id}/importar-finalizacion",
    response_model=FinalizacionImportResult,
    status_code=status.HTTP_201_CREATED,
)
async def importar_finalizacion(
    materia_id: UUID,
    cohorte_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_IMPORTAR),
) -> FinalizacionImportResult:
    current_user, scope = perm
    content = await file.read()
    try:
        return await _svc(db).importar_finalizacion(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            content=content,
            filename=file.filename or "upload",
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)


# ── F2.2 — atrasados ──────────────────────────────────────────────────────────


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/atrasados",
    response_model=AtrasadosResponse,
)
async def get_atrasados(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> AtrasadosResponse:
    current_user, scope = perm
    try:
        return await _svc(db).get_atrasados(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)


# ── F2.3 — ranking ────────────────────────────────────────────────────────────


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/ranking",
    response_model=RankingResponse,
)
async def get_ranking(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> RankingResponse:
    current_user, scope = perm
    try:
        return await _svc(db).get_ranking(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)


# ── F2.4 — reporte rápido ─────────────────────────────────────────────────────


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/reportes-rapidos",
    response_model=ReporteRapidoResponse,
)
async def get_reporte_rapido(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> ReporteRapidoResponse:
    current_user, scope = perm
    try:
        return await _svc(db).get_reporte_rapido(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)


# ── F2.5 — notas finales ──────────────────────────────────────────────────────


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/notas-finales",
    response_model=NotasFinalesResponse,
)
async def get_notas_finales(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> NotasFinalesResponse:
    current_user, scope = perm
    try:
        return await _svc(db).get_notas_finales(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/notas-finales/exportar",
)
async def exportar_notas_finales(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> Response:
    current_user, scope = perm
    try:
        csv_data = await _svc(db).exportar_notas_finales(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=notas_finales.csv"},
    )


# ── F2.6 — sin corregir ───────────────────────────────────────────────────────


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/sin-corregir",
    response_model=SinCorregirResponse,
)
async def get_sin_corregir(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_SIN_CORREGIR),
) -> SinCorregirResponse:
    current_user, scope = perm
    try:
        return await _svc(db).get_sin_corregir(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/sin-corregir/exportar",
)
async def exportar_sin_corregir(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_SIN_CORREGIR),
) -> Response:
    current_user, scope = perm
    try:
        csv_data = await _svc(db).exportar_sin_corregir(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            scope=scope,
        )
    except ValueError as exc:
        raise _http(exc)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sin_corregir.csv"},
    )


# ── F2.7/F2.8/F2.9 — monitor ─────────────────────────────────────────────────


@router.get(
    "/monitor",
    response_model=MonitorResponse,
)
async def get_monitor(
    materia_id: UUID | None = Query(None),
    cohorte_id: UUID | None = Query(None),
    alumno: str | None = Query(None),
    comision: str | None = Query(None),
    regional: str | None = Query(None),
    estado: str | None = Query(None, description="'atrasado' | 'al_dia'"),
    fecha_desde: str | None = Query(None),
    fecha_hasta: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> MonitorResponse:
    current_user, scope = perm
    try:
        return await _svc(db).get_monitor(
            current_user=current_user,
            scope=scope,
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            alumno=alumno,
            comision=comision,
            regional=regional,
            estado=estado,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise _http(exc)
