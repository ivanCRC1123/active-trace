"""Equipos endpoints — operaciones semánticas de equipo docente (C-08).

F4.2 mis-equipos: cualquier usuario autenticado ve sus propias asignaciones.
F4.3–F4.7: requieren ``equipos:asignar`` (COORDINADOR / ADMIN).
Prefix: /api/v1
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.equipos import (
    AsignacionEquipoResponse,
    AsignacionMasivaRequest,
    ClonarEquipoRequest,
    ClonarResult,
    EquipoFiltros,
    MasivaResult,
    MisEquiposFiltros,
    VigenciaBloqueRequest,
    VigenciaBloqueResult,
)
from app.services.equipo_service import EquipoService

from uuid import UUID
from datetime import date
from typing import Literal

router = APIRouter(prefix="/api/v1", tags=["equipos"])

_PERM = require_permission("equipos:asignar")


def _svc(db: AsyncSession) -> EquipoService:
    return EquipoService(db)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ── F4.2 mis-equipos ─────────────────────────────────────────────────────────

@router.get("/equipos/mis-equipos", response_model=list[AsignacionEquipoResponse])
async def mis_equipos(
    materia_id: UUID | None = Query(default=None),
    carrera_id: UUID | None = Query(default=None),
    cohorte_id: UUID | None = Query(default=None),
    rol: str | None = Query(default=None),
    estado_vigencia: Literal["Vigente", "Vencida"] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[AsignacionEquipoResponse]:
    filtros = MisEquiposFiltros(
        materia_id=materia_id,
        carrera_id=carrera_id,
        cohorte_id=cohorte_id,
        rol=rol,
        estado_vigencia=estado_vigencia,
    )
    return await _svc(db).mis_equipos(
        tenant_id=current_user.tenant_id,
        usuario_id=current_user.user_id,
        filtros=filtros,
    )


# ── F4.3 list equipo ──────────────────────────────────────────────────────────

@router.get("/equipos", response_model=list[AsignacionEquipoResponse])
async def list_equipo(
    materia_id: UUID | None = Query(default=None),
    carrera_id: UUID | None = Query(default=None),
    cohorte_id: UUID | None = Query(default=None),
    usuario_id: UUID | None = Query(default=None),
    responsable_id: UUID | None = Query(default=None),
    rol: str | None = Query(default=None),
    estado_vigencia: Literal["Vigente", "Vencida"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _auth: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> list[AsignacionEquipoResponse]:
    current_user, _ = _auth
    filtros = EquipoFiltros(
        materia_id=materia_id,
        carrera_id=carrera_id,
        cohorte_id=cohorte_id,
        usuario_id=usuario_id,
        responsable_id=responsable_id,
        rol=rol,
        estado_vigencia=estado_vigencia,
        limit=limit,
        offset=offset,
    )
    return await _svc(db).list_equipo(
        tenant_id=current_user.tenant_id,
        filtros=filtros,
    )


# ── F4.4 masiva ───────────────────────────────────────────────────────────────

@router.post("/equipos/masiva", response_model=MasivaResult, status_code=201)
async def asignar_masiva(
    body: AsignacionMasivaRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> MasivaResult:
    current_user, _ = _auth
    result = await _svc(db).asignar_masiva(
        tenant_id=current_user.tenant_id,
        payload=body,
        current_user=current_user,
        ip=_ip(request),
    )
    await db.commit()
    return result


# ── F4.5 clonar ───────────────────────────────────────────────────────────────

@router.post("/equipos/clonar", response_model=ClonarResult, status_code=201)
async def clonar_equipo(
    body: ClonarEquipoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> ClonarResult:
    current_user, _ = _auth
    result = await _svc(db).clonar_equipo(
        tenant_id=current_user.tenant_id,
        payload=body,
        current_user=current_user,
        ip=_ip(request),
    )
    await db.commit()
    return result


# ── F4.6 vigencia bloque ──────────────────────────────────────────────────────

@router.patch("/equipos/vigencia", response_model=VigenciaBloqueResult)
async def actualizar_vigencia_bloque(
    body: VigenciaBloqueRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> VigenciaBloqueResult:
    current_user, _ = _auth
    result = await _svc(db).actualizar_vigencia_bloque(
        tenant_id=current_user.tenant_id,
        payload=body,
        current_user=current_user,
        ip=_ip(request),
    )
    await db.commit()
    return result


# ── F4.7 exportar CSV ─────────────────────────────────────────────────────────

@router.get("/equipos/exportar")
async def exportar_csv(
    materia_id: UUID | None = Query(default=None),
    carrera_id: UUID | None = Query(default=None),
    cohorte_id: UUID | None = Query(default=None),
    usuario_id: UUID | None = Query(default=None),
    responsable_id: UUID | None = Query(default=None),
    rol: str | None = Query(default=None),
    estado_vigencia: Literal["Vigente", "Vencida"] | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _auth: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> StreamingResponse:
    current_user, _ = _auth
    filtros = EquipoFiltros(
        materia_id=materia_id,
        carrera_id=carrera_id,
        cohorte_id=cohorte_id,
        usuario_id=usuario_id,
        responsable_id=responsable_id,
        rol=rol,
        estado_vigencia=estado_vigencia,
    )
    csv_bytes = await _svc(db).exportar_csv(
        tenant_id=current_user.tenant_id,
        filtros=filtros,
    )
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="equipo.csv"'},
    )
