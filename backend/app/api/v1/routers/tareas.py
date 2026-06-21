"""Tareas endpoints — workflow de tareas internas (C-16, Épica 8).

F8.1 mis-tareas:   GET  /api/v1/tareas/mis-tareas  — identity only (TUTOR incluido)
F8.2 crear/estado: POST /api/v1/tareas             — require_permission gestionar
                   PATCH /api/v1/tareas/{id}/estado — identity + membership check
F8.3 admin global: GET  /api/v1/tareas             — require_permission gestionar (scope inyectado)
comentarios:       POST/GET /api/v1/tareas/{id}/comentarios — membership check
detalle:           GET  /api/v1/tareas/{id}         — membership check
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.core.permissions import check_permission, require_permission
from app.schemas.auth import CurrentUser
from app.schemas.tareas import (
    ComentarioCreateRequest,
    ComentarioResponse,
    MisTareasFiltros,
    TareaCreateRequest,
    TareaEstadoRequest,
    TareaFiltros,
    TareaResponse,
)
from app.services.tarea_service import TareaService
from typing import Literal

router = APIRouter(prefix="/api/v1", tags=["tareas"])

_PERM_GESTIONAR = require_permission("tareas_internas:gestionar", scoped=True)

_PERM_CODE = "tareas_internas:gestionar"


def _svc(db: AsyncSession) -> TareaService:
    return TareaService(db)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ── F8.1 mis-tareas ───────────────────────────────────────────────────────────

@router.get("/tareas/mis-tareas", response_model=list[TareaResponse])
async def mis_tareas(
    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"] | None = Query(default=None),
    materia_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[TareaResponse]:
    filtros = MisTareasFiltros(estado=estado, materia_id=materia_id, limit=limit, offset=offset)
    return await _svc(db).mis_tareas(
        tenant_id=current_user.tenant_id,
        usuario_id=current_user.user_id,
        filtros=filtros,
    )


# ── F8.2 crear tarea ──────────────────────────────────────────────────────────

@router.post("/tareas", response_model=TareaResponse, status_code=201)
async def crear_tarea(
    body: TareaCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: tuple[CurrentUser, str | None] = Depends(_PERM_GESTIONAR),
) -> TareaResponse:
    current_user, scope = _auth
    result = await _svc(db).crear_tarea(
        tenant_id=current_user.tenant_id,
        payload=body,
        current_user=current_user,
        scope=scope,
        ip=_ip(request),
    )
    await db.commit()
    return result


# ── GET detalle ───────────────────────────────────────────────────────────────

@router.get("/tareas/{tarea_id}", response_model=TareaResponse)
async def get_tarea(
    tarea_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TareaResponse:
    perm = await check_permission(current_user.user_id, current_user.tenant_id, _PERM_CODE, db)
    return await _svc(db).get_tarea(
        tarea_id=tarea_id,
        tenant_id=current_user.tenant_id,
        current_user=current_user,
        tiene_gestionar=perm.granted,
    )


# ── F8.2 cambiar estado ───────────────────────────────────────────────────────

@router.patch("/tareas/{tarea_id}/estado", response_model=TareaResponse)
async def cambiar_estado(
    tarea_id: UUID,
    body: TareaEstadoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TareaResponse:
    perm = await check_permission(current_user.user_id, current_user.tenant_id, _PERM_CODE, db)
    result = await _svc(db).cambiar_estado(
        tarea_id=tarea_id,
        tenant_id=current_user.tenant_id,
        nuevo_estado=body.estado,
        current_user=current_user,
        tiene_gestionar=perm.granted,
        ip=_ip(request),
    )
    await db.commit()
    return result


# ── F8.3 admin global ─────────────────────────────────────────────────────────

@router.get("/tareas", response_model=list[TareaResponse])
async def list_tareas(
    asignado_a: UUID | None = Query(default=None),
    asignado_por: UUID | None = Query(default=None),
    materia_id: UUID | None = Query(default=None),
    estado: Literal["Pendiente", "En progreso", "Resuelta", "Cancelada"] | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _auth: tuple[CurrentUser, str | None] = Depends(_PERM_GESTIONAR),
) -> list[TareaResponse]:
    current_user, scope = _auth
    filtros = TareaFiltros(
        asignado_a=asignado_a,
        asignado_por=asignado_por,
        materia_id=materia_id,
        estado=estado,
        q=q,
        limit=limit,
        offset=offset,
    )
    return await _svc(db).list_tareas(
        tenant_id=current_user.tenant_id,
        filtros=filtros,
        current_user=current_user,
        scope=scope,
    )


# ── Comentarios ───────────────────────────────────────────────────────────────

@router.post("/tareas/{tarea_id}/comentarios", response_model=ComentarioResponse, status_code=201)
async def agregar_comentario(
    tarea_id: UUID,
    body: ComentarioCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ComentarioResponse:
    perm = await check_permission(current_user.user_id, current_user.tenant_id, _PERM_CODE, db)
    result = await _svc(db).agregar_comentario(
        tarea_id=tarea_id,
        tenant_id=current_user.tenant_id,
        payload=body,
        current_user=current_user,
        tiene_gestionar=perm.granted,
    )
    await db.commit()
    return result


@router.get("/tareas/{tarea_id}/comentarios", response_model=list[ComentarioResponse])
async def list_comentarios(
    tarea_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ComentarioResponse]:
    perm = await check_permission(current_user.user_id, current_user.tenant_id, _PERM_CODE, db)
    return await _svc(db).list_comentarios(
        tarea_id=tarea_id,
        tenant_id=current_user.tenant_id,
        current_user=current_user,
        tiene_gestionar=perm.granted,
    )
