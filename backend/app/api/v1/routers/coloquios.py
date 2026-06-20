"""Coloquios endpoints — C-14 evaluaciones-y-coloquios.

Management (coloquios:gestionar) — ADMIN + COORDINADOR:
  GET    /api/v1/coloquios/                         list convocatorias
  POST   /api/v1/coloquios/                         create convocatoria
  GET    /api/v1/coloquios/metricas-panel            panel totals
  GET    /api/v1/coloquios/{id}                     get convocatoria
  PATCH  /api/v1/coloquios/{id}                     update convocatoria
  DELETE /api/v1/coloquios/{id}                     soft-delete convocatoria
  POST   /api/v1/coloquios/{id}/convocados          import convocados
  GET    /api/v1/coloquios/{id}/metricas            per-eval metrics
  GET    /api/v1/coloquios/{id}/reservas            list active reservas
  POST   /api/v1/coloquios/{id}/resultados          upsert resultado
  GET    /api/v1/coloquios/{id}/resultados          list resultados

Alumno (evaluacion:reservar):
  POST   /api/v1/coloquios/{id}/mis-reservas        make a reserva
  DELETE /api/v1/coloquios/{id}/mis-reservas/{rid}  cancel reserva
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.coloquios import (
    ConvocadoImportRequest,
    ConvocadoImportResponse,
    EvaluacionCreate,
    EvaluacionResponse,
    EvaluacionUpdate,
    MetricasConvocatoria,
    MetricasPanel,
    ReservaCreate,
    ReservaResponse,
    ResultadoCreate,
    ResultadoResponse,
)
from app.services.coloquios_service import ColoquiosService

router = APIRouter(prefix="/api/v1/coloquios", tags=["coloquios"])

_PERM_GESTIONAR = require_permission("coloquios:gestionar")
_PERM_RESERVAR = require_permission("evaluacion:reservar")


def _svc(db: AsyncSession) -> ColoquiosService:
    return ColoquiosService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "already exists" in msg or "sin_cupo" in msg or "reserva_already_active" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ── Management endpoints ───────────────────────────────────────────────────


@router.get("/metricas-panel", response_model=MetricasPanel)
async def metricas_panel(
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).metricas_panel(tenant_id=current_user.tenant_id)


@router.get("/", response_model=list[EvaluacionResponse])
async def list_convocatorias(
    materia_id: UUID | None = None,
    cohorte_id: UUID | None = None,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_convocatorias(
        tenant_id=current_user.tenant_id,
        materia_id=materia_id,
        cohorte_id=cohorte_id,
    )


@router.post("/", response_model=EvaluacionResponse, status_code=201)
async def create_convocatoria(
    body: EvaluacionCreate,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).create_convocatoria(
            tenant_id=current_user.tenant_id, data=body
        )
    except ValueError as exc:
        raise _http(exc)


@router.get("/{id}", response_model=EvaluacionResponse)
async def get_convocatoria(
    id: UUID,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_convocatoria(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router.patch("/{id}", response_model=EvaluacionResponse)
async def update_convocatoria(
    id: UUID,
    body: EvaluacionUpdate,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).update_convocatoria(
            id=id, tenant_id=current_user.tenant_id, data=body
        )
    except ValueError as exc:
        raise _http(exc)


@router.delete("/{id}", status_code=204)
async def delete_convocatoria(
    id: UUID,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).delete_convocatoria(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{id}/convocados", response_model=ConvocadoImportResponse, status_code=201)
async def importar_convocados(
    id: UUID,
    body: ConvocadoImportRequest,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        insertados = await _svc(db).importar_convocados(
            tenant_id=current_user.tenant_id,
            evaluacion_id=id,
            payload=body,
        )
    except ValueError as exc:
        raise _http(exc)
    return ConvocadoImportResponse(insertados=insertados)


@router.get("/{id}/metricas", response_model=MetricasConvocatoria)
async def metricas_convocatoria(
    id: UUID,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).metricas_convocatoria(
            tenant_id=current_user.tenant_id, evaluacion_id=id
        )
    except ValueError as exc:
        raise _http(exc)


@router.get("/{id}/reservas", response_model=list[ReservaResponse])
async def list_reservas(
    id: UUID,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).list_reservas(
            tenant_id=current_user.tenant_id, evaluacion_id=id
        )
    except ValueError as exc:
        raise _http(exc)


@router.post("/{id}/resultados", response_model=ResultadoResponse, status_code=201)
async def registrar_resultado(
    id: UUID,
    body: ResultadoCreate,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).registrar_resultado(
            tenant_id=current_user.tenant_id,
            evaluacion_id=id,
            alumno_id=body.alumno_id,
            nota_final=body.nota_final,
            current_user=current_user,
        )
    except ValueError as exc:
        raise _http(exc)


@router.get("/{id}/resultados", response_model=list[ResultadoResponse])
async def list_resultados(
    id: UUID,
    auth=Depends(_PERM_GESTIONAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).list_resultados(
            tenant_id=current_user.tenant_id, evaluacion_id=id
        )
    except ValueError as exc:
        raise _http(exc)


# ── Alumno endpoints ───────────────────────────────────────────────────────


@router.post("/{id}/mis-reservas", response_model=ReservaResponse, status_code=201)
async def reservar_turno(
    id: UUID,
    body: ReservaCreate,
    auth=Depends(_PERM_RESERVAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).reservar_turno(
            tenant_id=current_user.tenant_id,
            alumno_id=current_user.user_id,
            evaluacion_id=id,
            fecha_hora=body.fecha_hora,
        )
    except ValueError as exc:
        raise _http(exc)


@router.delete("/{id}/mis-reservas/{rid}", status_code=204)
async def cancelar_reserva(
    id: UUID,
    rid: UUID,
    auth=Depends(_PERM_RESERVAR),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).cancelar_reserva(
            tenant_id=current_user.tenant_id,
            alumno_id=current_user.user_id,
            evaluacion_id=id,
            reserva_id=rid,
        )
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
