"""Grilla salarial endpoints (C-18 — F10.1).

MateriaGrupo:  /api/v1/grilla-salarial/materia-grupos
SalarioBase:   /api/v1/grilla-salarial/salario-base
SalarioPlus:   /api/v1/grilla-salarial/salario-plus

All endpoints require ``grilla_salarial:operar`` (seeded for FINANZAS).
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.models.base import RolLiquidable
from app.schemas.grilla_salarial import (
    MateriaGrupoCreate,
    MateriaGrupoResponse,
    SalarioBaseCreate,
    SalarioBaseResponse,
    SalarioBaseUpdate,
    SalarioPlusCreate,
    SalarioPlusResponse,
    SalarioPlusUpdate,
)
from app.services.grilla_salarial_service import GrillaSalarialService

router_grilla = APIRouter(prefix="/api/v1/grilla-salarial", tags=["grilla-salarial"])

_PERM = require_permission("grilla_salarial:operar")


def _svc(db: AsyncSession) -> GrillaSalarialService:
    return GrillaSalarialService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "ya existe" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ── MateriaGrupo ────────────────────────────────────────────────────────────

@router_grilla.get("/materia-grupos", response_model=list[MateriaGrupoResponse])
async def list_materia_grupos(
    materia_id: UUID | None = None,
    grupo: str | None = None,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_materia_grupos(
        tenant_id=current_user.tenant_id,
        materia_id=materia_id,
        grupo=grupo,
    )


@router_grilla.post(
    "/materia-grupos", response_model=MateriaGrupoResponse, status_code=201
)
async def create_materia_grupo(
    body: MateriaGrupoCreate,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).create_materia_grupo(current_user=current_user, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_grilla.get("/materia-grupos/{id}", response_model=MateriaGrupoResponse)
async def get_materia_grupo(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_materia_grupo(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router_grilla.delete("/materia-grupos/{id}", status_code=204)
async def delete_materia_grupo(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).delete_materia_grupo(id=id, current_user=current_user)
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── SalarioBase ─────────────────────────────────────────────────────────────

@router_grilla.get("/salario-base", response_model=list[SalarioBaseResponse])
async def list_salario_base(
    rol: RolLiquidable | None = None,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_salario_base(
        tenant_id=current_user.tenant_id, rol=rol
    )


@router_grilla.get("/salario-base/vigente", response_model=SalarioBaseResponse | None)
async def get_salario_base_vigente(
    rol: RolLiquidable,
    fecha: date,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).get_salario_base_vigente(
        tenant_id=current_user.tenant_id, rol=rol, fecha=fecha
    )


@router_grilla.post("/salario-base", response_model=SalarioBaseResponse, status_code=201)
async def create_salario_base(
    body: SalarioBaseCreate,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).create_salario_base(current_user=current_user, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_grilla.get("/salario-base/{id}", response_model=SalarioBaseResponse)
async def get_salario_base(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_salario_base(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router_grilla.patch("/salario-base/{id}", response_model=SalarioBaseResponse)
async def update_salario_base(
    id: UUID,
    body: SalarioBaseUpdate,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).update_salario_base(
            id=id, current_user=current_user, data=body
        )
    except ValueError as exc:
        raise _http(exc)


@router_grilla.delete("/salario-base/{id}", status_code=204)
async def delete_salario_base(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).delete_salario_base(id=id, current_user=current_user)
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── SalarioPlus ─────────────────────────────────────────────────────────────

@router_grilla.get("/salario-plus", response_model=list[SalarioPlusResponse])
async def list_salario_plus(
    grupo: str | None = None,
    rol: RolLiquidable | None = None,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).list_salario_plus(
        tenant_id=current_user.tenant_id, grupo=grupo, rol=rol
    )


@router_grilla.get("/salario-plus/vigente", response_model=SalarioPlusResponse | None)
async def get_salario_plus_vigente(
    grupo: str,
    rol: RolLiquidable,
    fecha: date,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    return await _svc(db).get_salario_plus_vigente(
        tenant_id=current_user.tenant_id, grupo=grupo, rol=rol, fecha=fecha
    )


@router_grilla.post("/salario-plus", response_model=SalarioPlusResponse, status_code=201)
async def create_salario_plus(
    body: SalarioPlusCreate,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).create_salario_plus(current_user=current_user, data=body)
    except ValueError as exc:
        raise _http(exc)


@router_grilla.get("/salario-plus/{id}", response_model=SalarioPlusResponse)
async def get_salario_plus(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).get_salario_plus(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router_grilla.patch("/salario-plus/{id}", response_model=SalarioPlusResponse)
async def update_salario_plus(
    id: UUID,
    body: SalarioPlusUpdate,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        return await _svc(db).update_salario_plus(
            id=id, current_user=current_user, data=body
        )
    except ValueError as exc:
        raise _http(exc)


@router_grilla.delete("/salario-plus/{id}", status_code=204)
async def delete_salario_plus(
    id: UUID,
    auth=Depends(_PERM),
    db: AsyncSession = Depends(get_db),
):
    current_user, _ = auth
    try:
        await _svc(db).delete_salario_plus(id=id, current_user=current_user)
    except ValueError as exc:
        raise _http(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
