"""Router C-20 mensajería interna (F11.2).

GET  /api/v1/inbox                       — bandeja: hilos del usuario autenticado
POST /api/v1/inbox                       — crear hilo con participantes y mensaje inicial
GET  /api/v1/inbox/{hilo_id}             — detalle de hilo (solo participantes)
POST /api/v1/inbox/{hilo_id}/mensajes    — responder en hilo (solo participantes)
POST /api/v1/inbox/{hilo_id}/leer        — marcar hilo como leído (solo participantes)

Access control: toda operación sobre un hilo específico verifica participación.
No-participante → 403. Hilo de otro tenant → 404.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.schemas.auth import CurrentUser
from app.schemas.inbox import HiloCreate, HiloDetalle, HiloResponse, MensajeCreate, MensajeResponse
from app.services.inbox_service import InboxService

router = APIRouter(prefix="/api/v1/inbox", tags=["inbox"])


def _svc(db: AsyncSession) -> InboxService:
    return InboxService(db)


def _handle_exc(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "no_participante" in msg:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No participás en este hilo")
    if "hilo_no_encontrado" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hilo no encontrado")
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


@router.get("", response_model=list[HiloResponse])
async def listar_hilos(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[HiloResponse]:
    return await _svc(db).listar_hilos(current_user)


@router.post("", response_model=HiloDetalle, status_code=status.HTTP_201_CREATED)
async def crear_hilo(
    data: HiloCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HiloDetalle:
    try:
        return await _svc(db).crear_hilo(current_user, data)
    except (LookupError, PermissionError, ValueError) as exc:
        raise _handle_exc(exc)


@router.get("/{hilo_id}", response_model=HiloDetalle)
async def get_hilo(
    hilo_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HiloDetalle:
    try:
        return await _svc(db).get_hilo(current_user, hilo_id)
    except LookupError as exc:
        raise _handle_exc(exc)
    except PermissionError as exc:
        raise _handle_exc(exc)


@router.post("/{hilo_id}/mensajes", response_model=MensajeResponse, status_code=status.HTTP_201_CREATED)
async def responder(
    hilo_id: UUID,
    data: MensajeCreate,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MensajeResponse:
    try:
        return await _svc(db).responder(current_user, hilo_id, data)
    except LookupError as exc:
        raise _handle_exc(exc)
    except PermissionError as exc:
        raise _handle_exc(exc)


@router.post("/{hilo_id}/leer", status_code=status.HTTP_204_NO_CONTENT)
async def marcar_leido(
    hilo_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await _svc(db).marcar_leido(current_user, hilo_id)
    except LookupError as exc:
        raise _handle_exc(exc)
    except PermissionError as exc:
        raise _handle_exc(exc)
