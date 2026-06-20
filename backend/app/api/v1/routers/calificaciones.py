"""Calificaciones endpoints — grade import and threshold config (C-10).

Permissions:
  calificaciones:importar — import file, configure umbral, vaciar
  calificaciones:ver      — read grades

Prefix: /api/v1/calificaciones
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.calificaciones import (
    GradePreview,
    ImportarCalificacionesRequest,
    ImportarCalificacionesResult,
    UmbralMateriaRequest,
    UmbralMateriaResponse,
    VaciarResult,
)
from app.services.calificaciones_service import CalificacionesService

router = APIRouter(prefix="/api/v1/calificaciones", tags=["calificaciones"])

_PERM_IMPORTAR = require_permission("calificaciones:importar", scoped=True)
_PERM_VER = require_permission("calificaciones:ver")


def _svc(db: AsyncSession) -> CalificacionesService:
    return CalificacionesService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if msg in ("asignacion_not_found", "materia_not_found"):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post(
    "/{materia_id}/cohortes/{cohorte_id}/preview",
    response_model=GradePreview,
)
async def preview_calificaciones(
    materia_id: UUID,
    cohorte_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_IMPORTAR),
) -> GradePreview:
    content = await file.read()
    try:
        return await _svc(db).preview_file(content, file.filename or "upload")
    except ValueError as exc:
        raise _http(exc)


@router.post(
    "/{materia_id}/cohortes/{cohorte_id}/importar",
    response_model=ImportarCalificacionesResult,
    status_code=status.HTTP_201_CREATED,
)
async def importar_calificaciones(
    materia_id: UUID,
    cohorte_id: UUID,
    file: UploadFile = File(...),
    actividades_seleccionadas: list[str] = Query(...),
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_IMPORTAR),
) -> ImportarCalificacionesResult:
    current_user, _ = perm
    content = await file.read()
    request = ImportarCalificacionesRequest(actividades_seleccionadas=actividades_seleccionadas)
    try:
        return await _svc(db).importar(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            content=content,
            filename=file.filename or "upload",
            request=request,
        )
    except ValueError as exc:
        raise _http(exc)


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}",
)
async def get_calificaciones(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
):
    current_user, _ = perm
    try:
        return await _svc(db).list_calificaciones(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
        )
    except ValueError as exc:
        raise _http(exc)


@router.get(
    "/{materia_id}/cohortes/{cohorte_id}/umbral",
    response_model=UmbralMateriaResponse,
)
async def get_umbral(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_VER),
) -> UmbralMateriaResponse:
    current_user, _ = perm
    try:
        return await _svc(db).get_umbral(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
        )
    except ValueError as exc:
        raise _http(exc)


@router.put(
    "/{materia_id}/cohortes/{cohorte_id}/umbral",
    response_model=UmbralMateriaResponse,
)
async def upsert_umbral(
    materia_id: UUID,
    cohorte_id: UUID,
    request: UmbralMateriaRequest,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_IMPORTAR),
) -> UmbralMateriaResponse:
    current_user, _ = perm
    try:
        return await _svc(db).upsert_umbral(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            request=request,
        )
    except ValueError as exc:
        raise _http(exc)


@router.delete(
    "/{materia_id}/cohortes/{cohorte_id}/vaciar",
    response_model=VaciarResult,
)
async def vaciar_calificaciones(
    materia_id: UUID,
    cohorte_id: UUID,
    db: AsyncSession = Depends(get_db),
    perm: tuple[CurrentUser, str | None] = Depends(_PERM_IMPORTAR),
) -> VaciarResult:
    current_user, scope = perm
    try:
        return await _svc(db).vaciar(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            perm_scope=scope or "own",
        )
    except ValueError as exc:
        raise _http(exc)
