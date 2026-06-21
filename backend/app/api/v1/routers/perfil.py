"""Router C-20 perfil propio (F11.1).

GET  /api/v1/perfil  — ver perfil del usuario autenticado
PATCH /api/v1/perfil — actualizar campos editables

Self-only: identidad exclusivamente del JWT verificado.
Sin user_id en path ni body: no hay forma de apuntar a otro usuario.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.perfil import PerfilResponse, PerfilUpdate
from app.services.perfil_service import PerfilService

router = APIRouter(prefix="/api/v1/perfil", tags=["perfil"])


def _svc(db: AsyncSession) -> PerfilService:
    return PerfilService(db)


def _to_response(user) -> PerfilResponse:
    return PerfilResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        nombre=user.nombre,
        apellidos=user.apellidos,
        email=user.email_cifrado,       # EncryptedString ya descifró en SELECT
        sexo=user.sexo,
        dni=user.dni_cifrado,
        cuil=user.cuil_cifrado,
        cbu=user.cbu_cifrado,
        alias_cbu=user.alias_cbu_cifrado,
        banco=user.banco,
        regional=user.regional,
        legajo=user.legajo,
        legajo_profesional=user.legajo_profesional,
        facturador=user.facturador,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("", response_model=PerfilResponse)
async def get_perfil(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PerfilResponse:
    user = await _svc(db).get_propio(current_user)
    return _to_response(user)


@router.patch("", response_model=PerfilResponse)
async def update_perfil(
    data: PerfilUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PerfilResponse:
    try:
        user = await _svc(db).update_propio(current_user, data)
    except ValueError as exc:
        msg = str(exc)
        if "email_ya_registrado" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El email ya está registrado en este tenant",
            )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)
    return _to_response(user)
