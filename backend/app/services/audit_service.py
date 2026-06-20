"""AuditService — log business events and query the audit trail."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import VALID_ACTION_CODES
from app.repositories.audit_log_repository import AuditLogRepository
from app.schemas.auth import CurrentUser
from app.schemas.auditoria import AuditLogListResponse, AuditLogResponse


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        *,
        current_user: CurrentUser,
        accion: str,
        detalle: dict | None = None,
        filas_afectadas: int = 0,
        ip: str | None = None,
        user_agent: str | None = None,
        materia_id: UUID | None = None,
    ) -> None:
        if accion not in VALID_ACTION_CODES:
            raise ValueError(f"Unknown audit action code: {accion!r}")

        repo = AuditLogRepository(self._session, current_user.tenant_id)
        await repo.insert(
            actor_id=current_user.user_id,
            accion=accion,
            detalle=detalle,
            filas_afectadas=filas_afectadas,
            ip=ip,
            user_agent=user_agent,
            impersonado_id=current_user.impersonado_id,
            materia_id=materia_id,
        )

    async def list(
        self,
        *,
        tenant_id: UUID,
        scope: str,
        current_user_id: UUID,
        actor_id_filter: UUID | None = None,
        accion_filter: str | None = None,
        materia_id_filter: UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditLogListResponse:
        # scope='own' forces actor filter to the calling user, ignoring any actor_id param
        effective_actor_id = current_user_id if scope == "own" else actor_id_filter

        repo = AuditLogRepository(self._session, tenant_id)
        items, total = await repo.list(
            actor_id_filter=effective_actor_id,
            accion_filter=accion_filter,
            materia_id_filter=materia_id_filter,
            from_date=from_date,
            to_date=to_date,
            page=page,
            page_size=page_size,
        )

        return AuditLogListResponse(
            items=[
                AuditLogResponse(
                    id=entry.id,
                    fecha_hora=entry.fecha_hora,
                    actor_id=entry.actor_id,
                    impersonado_id=entry.impersonado_id,
                    materia_id=entry.materia_id,
                    accion=entry.accion,
                    detalle=entry.detalle,
                    filas_afectadas=entry.filas_afectadas,
                    ip=entry.ip,
                    user_agent=entry.user_agent,
                )
                for entry in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
