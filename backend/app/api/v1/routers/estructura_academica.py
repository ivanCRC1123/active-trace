"""Estructura académica endpoints — Carrera (E1), Cohorte (E2), Materia (E3).

All endpoints require ``estructura_academica:gestionar`` (ADMIN only).
Prefix: /api/v1/admin
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.estructura_academica import (
    CarreraCreate,
    CarreraResponse,
    CarreraUpdate,
    CohorteCreate,
    CohorteResponse,
    CohorteUpdate,
    MateriaCreate,
    MateriaResponse,
    MateriaUpdate,
)
from app.services.estructura_academica_service import EstructuraAcademicaService

router = APIRouter(prefix="/api/v1/admin", tags=["estructura-academica"])

_PERM = require_permission("estructura_academica:gestionar")


def _svc(db: AsyncSession) -> EstructuraAcademicaService:
    return EstructuraAcademicaService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "ya existe" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    if "inactiva" in msg:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


# ── Carreras ───────────────────────────────────────────────────────────────


@router.get("/carreras", response_model=list[CarreraResponse])
async def list_carreras(
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> list[CarreraResponse]:
    current_user, _ = _
    result = await _svc(db).list_carreras(tenant_id=current_user.tenant_id)
    return [CarreraResponse.model_validate(c) for c in result]


@router.post("/carreras", response_model=CarreraResponse, status_code=status.HTTP_201_CREATED)
async def create_carrera(
    body: CarreraCreate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> CarreraResponse:
    current_user, _ = _
    try:
        carrera = await _svc(db).create_carrera(tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        await db.refresh(carrera)
        return CarreraResponse.model_validate(carrera)
    except ValueError as exc:
        raise _http(exc)


@router.get("/carreras/{id}", response_model=CarreraResponse)
async def get_carrera(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> CarreraResponse:
    current_user, _ = _
    try:
        carrera = await _svc(db).get_carrera(id=id, tenant_id=current_user.tenant_id)
        return CarreraResponse.model_validate(carrera)
    except ValueError as exc:
        raise _http(exc)


@router.patch("/carreras/{id}", response_model=CarreraResponse)
async def update_carrera(
    id: UUID,
    body: CarreraUpdate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> CarreraResponse:
    current_user, _ = _
    try:
        carrera = await _svc(db).update_carrera(id=id, tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        await db.refresh(carrera)
        return CarreraResponse.model_validate(carrera)
    except ValueError as exc:
        raise _http(exc)


@router.delete("/carreras/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_carrera(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> Response:
    current_user, _ = _
    try:
        await _svc(db).delete_carrera(id=id, tenant_id=current_user.tenant_id)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        raise _http(exc)


# ── Cohortes ───────────────────────────────────────────────────────────────


@router.get("/cohortes", response_model=list[CohorteResponse])
async def list_cohortes(
    carrera_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> list[CohorteResponse]:
    current_user, _ = _
    result = await _svc(db).list_cohortes(
        tenant_id=current_user.tenant_id, carrera_id=carrera_id
    )
    return [CohorteResponse.model_validate(c) for c in result]


@router.post("/cohortes", response_model=CohorteResponse, status_code=status.HTTP_201_CREATED)
async def create_cohorte(
    body: CohorteCreate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> CohorteResponse:
    current_user, _ = _
    try:
        cohorte = await _svc(db).create_cohorte(tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        await db.refresh(cohorte)
        return CohorteResponse.model_validate(cohorte)
    except ValueError as exc:
        raise _http(exc)


@router.get("/cohortes/{id}", response_model=CohorteResponse)
async def get_cohorte(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> CohorteResponse:
    current_user, _ = _
    try:
        cohorte = await _svc(db).get_cohorte(id=id, tenant_id=current_user.tenant_id)
        return CohorteResponse.model_validate(cohorte)
    except ValueError as exc:
        raise _http(exc)


@router.patch("/cohortes/{id}", response_model=CohorteResponse)
async def update_cohorte(
    id: UUID,
    body: CohorteUpdate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> CohorteResponse:
    current_user, _ = _
    try:
        cohorte = await _svc(db).update_cohorte(id=id, tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        await db.refresh(cohorte)
        return CohorteResponse.model_validate(cohorte)
    except ValueError as exc:
        raise _http(exc)


@router.delete("/cohortes/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohorte(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> Response:
    current_user, _ = _
    try:
        await _svc(db).delete_cohorte(id=id, tenant_id=current_user.tenant_id)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        raise _http(exc)


# ── Materias ───────────────────────────────────────────────────────────────


@router.get("/materias", response_model=list[MateriaResponse])
async def list_materias(
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> list[MateriaResponse]:
    current_user, _ = _
    result = await _svc(db).list_materias(tenant_id=current_user.tenant_id)
    return [MateriaResponse.model_validate(m) for m in result]


@router.post("/materias", response_model=MateriaResponse, status_code=status.HTTP_201_CREATED)
async def create_materia(
    body: MateriaCreate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> MateriaResponse:
    current_user, _ = _
    try:
        materia = await _svc(db).create_materia(tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        await db.refresh(materia)
        return MateriaResponse.model_validate(materia)
    except ValueError as exc:
        raise _http(exc)


@router.get("/materias/{id}", response_model=MateriaResponse)
async def get_materia(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> MateriaResponse:
    current_user, _ = _
    try:
        materia = await _svc(db).get_materia(id=id, tenant_id=current_user.tenant_id)
        return MateriaResponse.model_validate(materia)
    except ValueError as exc:
        raise _http(exc)


@router.patch("/materias/{id}", response_model=MateriaResponse)
async def update_materia(
    id: UUID,
    body: MateriaUpdate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> MateriaResponse:
    current_user, _ = _
    try:
        materia = await _svc(db).update_materia(id=id, tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        await db.refresh(materia)
        return MateriaResponse.model_validate(materia)
    except ValueError as exc:
        raise _http(exc)


@router.delete("/materias/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_materia(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> Response:
    current_user, _ = _
    try:
        await _svc(db).delete_materia(id=id, tenant_id=current_user.tenant_id)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        raise _http(exc)
