"""Audit log query endpoint.

GET /api/v1/auditoria — paginated, filtered view of the audit trail.
Requires auditoria:ver permission. Scope determines visibility:
  - scope='all' (ADMIN, FINANZAS): all entries for the tenant
  - scope='own' (COORDINADOR): only entries where actor_id == current user
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.permissions import require_permission
from app.schemas.auth import CurrentUser
from app.schemas.auditoria import AuditLogListResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1/auditoria", tags=["auditoria"])


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
    _: tuple[CurrentUser, str | None] = Depends(
        require_permission("auditoria:ver", scoped=True)
    ),
) -> AuditLogListResponse:
    """List audit log entries for the current tenant.

    Results are filtered by scope: ADMIN/FINANZAS see all entries;
    COORDINADOR sees only entries where actor_id matches their own user_id.
    """
    current_user, scope = _

    service = AuditService(db)
    return await service.list(
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
