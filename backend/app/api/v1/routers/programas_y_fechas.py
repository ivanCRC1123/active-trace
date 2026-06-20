"""Programas y fechas académicas endpoints.

ProgramaMateria (E16): /api/v1/programas  — requires ``programas:gestionar``
FechaAcademica  (E15): /api/v1/fechas-academicas — requires ``fechas_academicas:gestionar``

Both permissions are seeded for ADMIN + COORDINADOR (C-17).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.programas_y_fechas import (
    FechaAcademicaCreate,
    FechaAcademicaResponse,
    FechaAcademicaUpdate,
    ProgramaMateriaCreate,
    ProgramaMateriaResponse,
    ProgramaMateriaUpdate,
)
from app.services.programas_service import ProgramasService

router_programas = APIRouter(prefix="/api/v1/programas", tags=["programas"])
router_fechas = APIRouter(prefix="/api/v1/fechas-academicas", tags=["fechas-academicas"])

_PERM_PROGRAMAS = require_permission("programas:gestionar")
_PERM_FECHAS = require_permission("fechas_academicas:gestionar")


def _svc(db: AsyncSession) -> ProgramasService:
    return ProgramasService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "ya existe" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ── ProgramaMateria ────────────────────────────────────────────────────────


@router_programas.get("/", response_model=list[ProgramaMateriaResponse])
async def list_programas(
    materia_id: UUID | None = None,
    carrera_id: UUID | None = None,
    cohorte_id: UUID | None = None,
    auth=Depends(_PERM_PROGRAMAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_programas(
        tenant_id=current_user.tenant_id,
        materia_id=materia_id,
        carrera_id=carrera_id,
        cohorte_id=cohorte_id,
    )


@router_programas.post("/", response_model=ProgramaMateriaResponse, status_code=201)
async def create_programa(
    body: ProgramaMateriaCreate,
    auth=Depends(_PERM_PROGRAMAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).create_programa(tenant_id=current_user.tenant_id, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_programas.get("/{id}", response_model=ProgramaMateriaResponse)
async def get_programa(
    id: UUID,
    auth=Depends(_PERM_PROGRAMAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_programa(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router_programas.patch("/{id}", response_model=ProgramaMateriaResponse)
async def update_programa(
    id: UUID,
    body: ProgramaMateriaUpdate,
    auth=Depends(_PERM_PROGRAMAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).update_programa(
            id=id, tenant_id=current_user.tenant_id, data=body
        )
    except ValueError as exc:
        raise _http(exc)


@router_programas.delete("/{id}", status_code=204)
async def delete_programa(
    id: UUID,
    auth=Depends(_PERM_PROGRAMAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).delete_programa(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── FechaAcademica ─────────────────────────────────────────────────────────


@router_fechas.get("/fragmento-lms")
async def fragmento_lms(
    materia_id: UUID,
    cohorte_id: UUID,
    periodo: str | None = None,
    auth=Depends(_PERM_FECHAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    fragmento = await _svc(db).generar_fragmento_lms(
        tenant_id=current_user.tenant_id,
        materia_id=materia_id,
        cohorte_id=cohorte_id,
        periodo=periodo,
    )
    return {"fragmento": fragmento}


@router_fechas.get("/", response_model=list[FechaAcademicaResponse])
async def list_fechas(
    materia_id: UUID | None = None,
    cohorte_id: UUID | None = None,
    periodo: str | None = None,
    auth=Depends(_PERM_FECHAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_fechas(
        tenant_id=current_user.tenant_id,
        materia_id=materia_id,
        cohorte_id=cohorte_id,
        periodo=periodo,
    )


@router_fechas.post("/", response_model=FechaAcademicaResponse, status_code=201)
async def create_fecha(
    body: FechaAcademicaCreate,
    auth=Depends(_PERM_FECHAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).create_fecha(tenant_id=current_user.tenant_id, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_fechas.get("/{id}", response_model=FechaAcademicaResponse)
async def get_fecha(
    id: UUID,
    auth=Depends(_PERM_FECHAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_fecha(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router_fechas.patch("/{id}", response_model=FechaAcademicaResponse)
async def update_fecha(
    id: UUID,
    body: FechaAcademicaUpdate,
    auth=Depends(_PERM_FECHAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).update_fecha(
            id=id, tenant_id=current_user.tenant_id, data=body
        )
    except ValueError as exc:
        raise _http(exc)


@router_fechas.delete("/{id}", status_code=204)
async def delete_fecha(
    id: UUID,
    auth=Depends(_PERM_FECHAS),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).delete_fecha(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
