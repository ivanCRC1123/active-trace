"""Audit log query endpoints (C-05 legacy + C-19 panel).

C-05: GET /api/v1/auditoria — paginated list (scope: own = actor filter)
C-19: GET /api/v1/auditoria/panel/* — aggregated panel views (scope: own = materia filter)
      GET /api/v1/auditoria/log    — paginated log with resolved names and dual schema
"""

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.auditoria import (
    AccionesXDiaResponse,
    AuditLogListResponse,
    ComunicacionesDocenteResponse,
    InteraccionesResponse,
    PaginatedAuditLogResponse,
    UltimasAccionesResponse,
)
from app.services.audit_service import AuditService
from app.services.auditoria_service import AuditoriaService

router = APIRouter(prefix="/api/v1/auditoria", tags=["auditoria"])

_PERM = require_permission("auditoria:ver", scoped=True)


# ── C-05 — legacy list (actor-scoped) ────────────────────────────────────────


@router.get("", response_model=AuditLogListResponse)
async def list_audit_log(
    actor_id: UUID | None = None,
    accion: str | None = None,
    materia_id: UUID | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> AuditLogListResponse:
    """List audit log entries for the current tenant (C-05).

    COORDINATOR scope filters by actor_id == self; ADMIN/FINANZAS see all.
    """
    current_user, scope = _
    return await AuditService(db).list(
        tenant_id=current_user.tenant_id,
        scope=scope or "all",
        current_user_id=current_user.user_id,
        actor_id_filter=actor_id,
        accion_filter=accion,
        materia_id_filter=materia_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )


# ── C-19 — panel/acciones-por-dia ────────────────────────────────────────────


@router.get("/panel/acciones-por-dia", response_model=AccionesXDiaResponse)
async def panel_acciones_por_dia(
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> AccionesXDiaResponse:
    current_user, scope = _
    return await AuditoriaService(db).get_acciones_por_dia(
        current_user=current_user,
        scope=scope,
        from_date=from_date,
        to_date=to_date,
    )


# ── C-19 — panel/comunicaciones-docente ──────────────────────────────────────


@router.get("/panel/comunicaciones-docente", response_model=ComunicacionesDocenteResponse)
async def panel_comunicaciones_docente(
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> ComunicacionesDocenteResponse:
    current_user, scope = _
    return await AuditoriaService(db).get_comunicaciones_docente(
        current_user=current_user,
        scope=scope,
    )


# ── C-19 — panel/interacciones ────────────────────────────────────────────────


@router.get("/panel/interacciones", response_model=InteraccionesResponse)
async def panel_interacciones(
    from_date: date | None = None,
    to_date: date | None = None,
    actor_id: UUID | None = None,
    accion: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> InteraccionesResponse:
    current_user, scope = _
    return await AuditoriaService(db).get_interacciones(
        current_user=current_user,
        scope=scope,
        from_date=from_date,
        to_date=to_date,
        actor_id=actor_id,
        accion=accion,
    )


# ── C-19 — panel/ultimas-acciones ────────────────────────────────────────────


@router.get("/panel/ultimas-acciones", response_model=UltimasAccionesResponse)
async def panel_ultimas_acciones(
    limit: int = Query(default=200, ge=1, le=500),
    from_date: date | None = None,
    to_date: date | None = None,
    actor_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> UltimasAccionesResponse:
    current_user, scope = _
    return await AuditoriaService(db).get_ultimas_acciones(
        current_user=current_user,
        scope=scope,
        limit=limit,
        from_date=from_date,
        to_date=to_date,
        actor_id=actor_id,
    )


# ── C-19 — log completo (dual schema) ────────────────────────────────────────


@router.get("/log", response_model=PaginatedAuditLogResponse)
async def log_completo(
    from_date: date | None = None,
    to_date: date | None = None,
    actor_id: UUID | None = None,
    accion: str | None = None,
    materia_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: tuple[CurrentUser, str | None] = Depends(_PERM),
) -> PaginatedAuditLogResponse:
    current_user, scope = _
    return await AuditoriaService(db).get_log_completo(
        current_user=current_user,
        scope=scope,
        from_date=from_date,
        to_date=to_date,
        actor_id=actor_id,
        accion=accion,
        materia_id=materia_id,
        page=page,
        page_size=page_size,
    )
