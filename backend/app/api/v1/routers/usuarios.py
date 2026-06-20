"""Usuarios endpoints — ABM de usuarios con PII cifrada (C-07).

Permission required: ``usuarios:gestionar`` (ADMIN).
Prefix: /api/v1/admin
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.usuarios import UsuarioCreate, UsuarioResponse, UsuarioUpdate
from app.services.usuario_service import UsuarioService

router = APIRouter(prefix="/api/v1/admin", tags=["usuarios"])

_PERM = require_permission("usuarios:gestionar")


def _svc(db: AsyncSession) -> UsuarioService:
    return UsuarioService(db)


def _http(exc: ValueError) -> HTTPException:
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "email ya existe" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get("/usuarios", response_model=list[UsuarioResponse])
async def list_usuarios(
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> list[UsuarioResponse]:
    current_user, _ = _
    return await _svc(db).list_usuarios(tenant_id=current_user.tenant_id)


@router.post("/usuarios", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def create_usuario(
    body: UsuarioCreate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> UsuarioResponse:
    current_user, _ = _
    try:
        resp = await _svc(db).create_usuario(tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        return resp
    except ValueError as exc:
        raise _http(exc)


@router.get("/usuarios/{id}", response_model=UsuarioResponse)
async def get_usuario(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> UsuarioResponse:
    current_user, _ = _
    try:
        return await _svc(db).get_usuario(id=id, tenant_id=current_user.tenant_id)
    except ValueError as exc:
        raise _http(exc)


@router.patch("/usuarios/{id}", response_model=UsuarioResponse)
async def update_usuario(
    id: UUID,
    body: UsuarioUpdate,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> UsuarioResponse:
    current_user, _ = _
    try:
        resp = await _svc(db).update_usuario(id=id, tenant_id=current_user.tenant_id, data=body)
        await db.commit()
        return resp
    except ValueError as exc:
        raise _http(exc)


@router.delete("/usuarios/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_usuario(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> Response:
    current_user, _ = _
    try:
        await _svc(db).delete_usuario(id=id, tenant_id=current_user.tenant_id)
        await db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as exc:
        raise _http(exc)
