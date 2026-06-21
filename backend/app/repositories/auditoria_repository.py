"""AuditoriaRepository — read-only panel queries over audit_log (C-19).

Separate from AuditLogRepository (C-05, insert concern) to preserve SRP.
All methods are tenant-scoped. materia_ids=None means no filter (scope=all);
materia_ids=set() means empty result (COORDINATOR with no active asignaciones).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import cast, func, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from app.models.audit_log import AuditLog


@dataclass(frozen=True)
class AccionPorDiaRow:
    fecha: date
    cantidad: int


@dataclass(frozen=True)
class InteraccionRow:
    actor_id: UUID
    materia_id: UUID | None
    accion: str
    cantidad: int


class AuditoriaRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    # ── helpers ──────────────────────────────────────────────────────────────

    def _base(self):
        return select(AuditLog).where(AuditLog.tenant_id == self._tenant_id)

    def _apply_date_range(self, stmt, from_date: date | None, to_date: date | None):
        if from_date is not None:
            dt_from = datetime(from_date.year, from_date.month, from_date.day, tzinfo=timezone.utc)
            stmt = stmt.where(AuditLog.fecha_hora >= dt_from)
        if to_date is not None:
            dt_to = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=timezone.utc)
            stmt = stmt.where(AuditLog.fecha_hora <= dt_to)
        return stmt

    def _apply_materia_filter(self, stmt, materia_ids: set[UUID] | None):
        if materia_ids is None:
            return stmt
        return stmt.where(AuditLog.materia_id.in_(materia_ids))

    # ── F9.1(a) — acciones por día ────────────────────────────────────────────

    async def acciones_por_dia(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        materia_ids: set[UUID] | None = None,
    ) -> list[AccionPorDiaRow]:
        if materia_ids is not None and len(materia_ids) == 0:
            return []

        fecha_col = cast(AuditLog.fecha_hora, Date).label("fecha")
        stmt = (
            select(fecha_col, func.count().label("cantidad"))
            .where(AuditLog.tenant_id == self._tenant_id)
        )
        stmt = self._apply_date_range(stmt, from_date, to_date)
        stmt = self._apply_materia_filter(stmt, materia_ids)
        stmt = stmt.group_by(fecha_col).order_by(fecha_col)

        rows = (await self._session.execute(stmt)).all()
        return [AccionPorDiaRow(fecha=r.fecha, cantidad=r.cantidad) for r in rows]

    # ── F9.1(c) — interacciones por docente y materia ────────────────────────

    async def interacciones_por_docente_materia(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        actor_id_filter: UUID | None = None,
        accion_filter: str | None = None,
        materia_ids: set[UUID] | None = None,
    ) -> list[InteraccionRow]:
        if materia_ids is not None and len(materia_ids) == 0:
            return []

        stmt = (
            select(
                AuditLog.actor_id,
                AuditLog.materia_id,
                AuditLog.accion,
                func.count().label("cantidad"),
            )
            .where(AuditLog.tenant_id == self._tenant_id)
        )
        stmt = self._apply_date_range(stmt, from_date, to_date)
        stmt = self._apply_materia_filter(stmt, materia_ids)
        if actor_id_filter is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id_filter)
        if accion_filter is not None:
            stmt = stmt.where(AuditLog.accion == accion_filter)
        stmt = (
            stmt.group_by(AuditLog.actor_id, AuditLog.materia_id, AuditLog.accion)
            .order_by(text("cantidad DESC"))
        )

        rows = (await self._session.execute(stmt)).all()
        return [
            InteraccionRow(
                actor_id=r.actor_id,
                materia_id=r.materia_id,
                accion=r.accion,
                cantidad=r.cantidad,
            )
            for r in rows
        ]

    # ── F9.1(d) — últimas acciones ────────────────────────────────────────────

    async def ultimas_acciones(
        self,
        *,
        limit: int = 200,
        from_date: date | None = None,
        to_date: date | None = None,
        actor_id_filter: UUID | None = None,
        materia_ids: set[UUID] | None = None,
    ) -> list[AuditLog]:
        if materia_ids is not None and len(materia_ids) == 0:
            return []

        stmt = select(AuditLog).where(AuditLog.tenant_id == self._tenant_id)
        stmt = self._apply_date_range(stmt, from_date, to_date)
        stmt = self._apply_materia_filter(stmt, materia_ids)
        if actor_id_filter is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id_filter)
        stmt = stmt.order_by(AuditLog.fecha_hora.desc()).limit(limit)

        return list((await self._session.execute(stmt)).scalars().all())

    # ── F9.2 — log completo paginado ─────────────────────────────────────────

    async def log_completo(
        self,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
        actor_id_filter: UUID | None = None,
        accion_filter: str | None = None,
        materia_ids: set[UUID] | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        if materia_ids is not None and len(materia_ids) == 0:
            return [], 0

        stmt = select(AuditLog).where(AuditLog.tenant_id == self._tenant_id)
        stmt = self._apply_date_range(stmt, from_date, to_date)
        stmt = self._apply_materia_filter(stmt, materia_ids)
        if actor_id_filter is not None:
            stmt = stmt.where(AuditLog.actor_id == actor_id_filter)
        if accion_filter is not None:
            stmt = stmt.where(AuditLog.accion == accion_filter)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total: int = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(AuditLog.fecha_hora.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        items = list((await self._session.execute(stmt)).scalars().all())
        return items, total
