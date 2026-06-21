"""Router C-13 encuentros (F6.1–F6.5).

POST   /api/v1/encuentros/slots                      — crear slot + instancias
GET    /api/v1/encuentros/slots                      — listar slots
GET    /api/v1/encuentros/slots/{slot_id}            — detalle slot + instancias
DELETE /api/v1/encuentros/slots/{slot_id}            — soft-delete + cancela Programadas
GET    /api/v1/encuentros/instancias                 — listar instancias
PATCH  /api/v1/encuentros/instancias/{instancia_id}  — editar instancia (F6.3)
GET    /api/v1/encuentros/fragmento-lms              — fragmento Markdown (F6.4)

RBAC: encuentros:gestionar (TUTOR=all, PROFESOR=own, COORDINADOR=all, ADMIN=all)
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.encuentros import (
    FragmentoLMSResponse,
    InstanciaResponse,
    InstanciaUpdate,
    SlotConInstanciasResponse,
    SlotCreate,
    SlotResponse,
)
from app.services.encuentro_service import EncuentroService

router = APIRouter(prefix="/api/v1/encuentros", tags=["encuentros"])

_PERM = require_permission("encuentros:gestionar", scoped=True)


def _svc(db: AsyncSession) -> EncuentroService:
    return EncuentroService(db)


def _handle(exc: Exception) -> HTTPException:
    msg = str(exc)
    if "no_encontrad" in msg or "no_propi" in msg and "no_encontrad" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    if "no_propi" in msg or "no_participante" in msg or "asignacion_no_propia" in msg:
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
    if "no_encontrad" in msg:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)


@router.post("/slots", response_model=SlotConInstanciasResponse, status_code=status.HTTP_201_CREATED)
async def crear_slot(
    data: SlotCreate,
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> SlotConInstanciasResponse:
    current_user, scope = auth
    try:
        return await _svc(db).crear_slot(current_user, data, scope)
    except (ValueError, PermissionError, LookupError) as exc:
        raise _handle(exc)


@router.get("/slots", response_model=list[SlotResponse])
async def listar_slots(
    materia_id: Optional[UUID] = Query(default=None),
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> list[SlotResponse]:
    current_user, scope = auth
    return await _svc(db).listar_slots(current_user, scope, materia_id)


@router.get("/slots/{slot_id}", response_model=SlotConInstanciasResponse)
async def get_slot(
    slot_id: UUID,
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> SlotConInstanciasResponse:
    current_user, scope = auth
    try:
        return await _svc(db).get_slot(current_user, slot_id, scope)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.delete("/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_slot(
    slot_id: UUID,
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> None:
    current_user, scope = auth
    try:
        await _svc(db).eliminar_slot(current_user, slot_id, scope)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/instancias", response_model=list[InstanciaResponse])
async def listar_instancias(
    materia_id: Optional[UUID] = Query(default=None),
    slot_id: Optional[UUID] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    fecha_desde: Optional[date] = Query(default=None),
    fecha_hasta: Optional[date] = Query(default=None),
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> list[InstanciaResponse]:
    current_user, scope = auth
    return await _svc(db).listar_instancias(
        current_user, scope, materia_id, slot_id, estado, fecha_desde, fecha_hasta
    )


@router.patch("/instancias/{instancia_id}", response_model=InstanciaResponse)
async def editar_instancia(
    instancia_id: UUID,
    data: InstanciaUpdate,
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> InstanciaResponse:
    current_user, scope = auth
    try:
        return await _svc(db).editar_instancia(current_user, instancia_id, data, scope)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/fragmento-lms", response_model=FragmentoLMSResponse)
async def fragmento_lms(
    materia_id: UUID = Query(...),
    slot_id: Optional[UUID] = Query(default=None),
    auth: tuple[CurrentUser, str | None] = Depends(_PERM),
    db: AsyncSession = Depends(get_db),
) -> FragmentoLMSResponse:
    current_user, scope = auth
    return await _svc(db).fragmento_lms(current_user, scope, materia_id, slot_id)
