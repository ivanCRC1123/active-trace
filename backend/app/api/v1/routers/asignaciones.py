"""Asignaciones endpoints — vínculo docente–contexto académico (C-07).

Permission required: ``equipos:asignar``.
Prefix: /api/v1
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.asignaciones import AsignacionCreate, AsignacionResponse, AsignacionUpdate
from app.schemas.auth import CurrentUser
from app.services.asignacion_service import AsignacionService

router = APIRouter(prefix="/api/v1", tags=["asignaciones"])

_PERM = require_permission("equipos:asignar")


def _svc(db: AsyncSession) -> AsignacionService:
    return AsignacionService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get("/asignaciones", response_model=list[AsignacionResponse])
async def list_asignaciones(
    vigente: bool | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> list[AsignacionResponse]:
    current_user, _ = _
    return await _svc(db).list_asignaciones(
        tenant_id=current_user.tenant_id, vigente=vigente
    )


@router.post(
    "/asignaciones",
    response_model=AsignacionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_asignacion(
    body: AsignacionCreate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> AsignacionResponse:
    current_user, _ = _
    try:
        resp = await _svc(db).create_asignacion(tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        return resp
    except ValueError as exc:
        raise _http(exc)


@router.get("/asignaciones/{id}", response_model=AsignacionResponse)
async def get_asignacion(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> AsignacionResponse:
    current_user, _ = _
    try:
        return await _svc(db).get_asignacion(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router.patch("/asignaciones/{id}", response_model=AsignacionResponse)
async def update_asignacion(
    id: UUID,
    body: AsignacionUpdate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> AsignacionResponse:
    current_user, _ = _
    try:
        resp = await _svc(db).update_asignacion(
            id=id, tenant_id=current_user.tenant_id, data=body
        )
        await db.commit()
        return resp
    except ValueError as exc:
        raise _http(exc)


@router.delete("/asignaciones/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asignacion(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> Response:
    current_user, _ = _
    try:
        await _svc(db).delete_asignacion(id=id, tenant_id=current_user.tenant_id)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        raise _http(exc)
