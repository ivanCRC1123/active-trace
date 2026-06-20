"""Append-only repository for AuditLog entries.

Exposes only insert() and list() — no update(), delete(), or soft_delete().
All queries are automatically scoped to the repository's tenant_id.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def insert(
        self,
        *,
        actor_id: UUID,
        accion: str,
        detalle: dict | None = None,
        filas_afectadas: int = 0,
        ip: str | None = None,
        user_agent: str | None = None,
        impersonado_id: UUID | None = None,
        materia_id: UUID | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            tenant_id=self._tenant_id,
            actor_id=actor_id,
            accion=accion,
            detalle=detalle,
            filas_afectadas=filas_afectadas,
            ip=ip,
            user_agent=user_agent,
            impersonado_id=impersonado_id,
            materia_id=materia_id,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def list(
        self,
        *,
        actor_id_filter: UUID | None = None,
        accion_filter: str | None = None,
        materia_id_filter: UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog).where(AuditLog.tenant_id == self._tenant_id)

        if actor_id_filter is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id_filter)
        if accion_filter is not None:
            stmt = stmt.where(AuditLog.accion == accion_filter)
        if materia_id_filter is not None:
            stmt = stmt.where(AuditLog.materia_id == materia_id_filter)
        if from_date is not None:
            stmt = stmt.where(AuditLog.fecha_hora >= from_date)
        if to_date is not None:
            stmt = stmt.where(AuditLog.fecha_hora <= to_date)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total: int = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(AuditLog.fecha_hora.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        return items, total
