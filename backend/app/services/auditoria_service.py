"""AuditoriaService — C-19 panel de auditoría y métricas (read-only).

Separate from AuditService (C-05, handles insert + legacy list).
All panel queries are tenant-scoped and RBAC-scoped via materia_ids.
"""

from __future__ import annotations

import math
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asignacion import Asignacion
from app.models.user import User
from app.repositories.auditoria_repository import AuditoriaRepository
from app.repositories.comunicacion_repository import ComunicacionRepository
from app.schemas.auditoria import (
    AccionXDia,
    AccionesXDiaResponse,
    AuditLogFullEntry,
    AuditLogPublicEntry,
    ComunicacionesDocenteResponse,
    EstadoComunicacionXDocente,
    InteraccionXDocenteMateria,
    InteraccionesResponse,
    PaginatedAuditLogResponse,
    UltimasAccionesResponse,
)
from app.schemas.auth import CurrentUser


class AuditoriaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── RBAC scoping ─────────────────────────────────────────────────────────

    async def _get_materia_ids_scoped(
        self, *, actor_id: UUID, tenant_id: UUID, scope: str
    ) -> set[UUID] | None:
        """Resolve visible materia_ids based on scope.

        scope='all'  → None (no materia filter)
        scope='own'  → set of materia_ids the user is assigned to
                       (empty set if coordinator has no active asignaciones)
        """
        if scope == "all":
            return None
        stmt = select(Asignacion.materia_id).where(
            Asignacion.tenant_id == tenant_id,
            Asignacion.usuario_id == actor_id,
            Asignacion.deleted_at.is_(None),
            Asignacion.materia_id.is_not(None),
        ).distinct()
        rows = (await self._session.execute(stmt)).all()
        return {r[0] for r in rows}

    # ── User name resolution ──────────────────────────────────────────────────

    async def _resolve_users(
        self, ids: set[UUID], tenant_id: UUID
    ) -> dict[UUID, dict[str, str]]:
        if not ids:
            return {}
        stmt = select(User.id, User.nombre, User.apellidos).where(
            User.id.in_(ids),
            User.tenant_id == tenant_id,
            User.deleted_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).all()
        return {r.id: {"nombre": r.nombre, "apellidos": r.apellidos} for r in rows}

    # ── F9.1(a) — acciones por día ────────────────────────────────────────────

    async def get_acciones_por_dia(
        self,
        *,
        current_user: CurrentUser,
        scope: str | None,
        from_date=None,
        to_date=None,
    ) -> AccionesXDiaResponse:
        effective_scope = scope or "all"
        materia_ids = await self._get_materia_ids_scoped(
            actor_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            scope=effective_scope,
        )
        repo = AuditoriaRepository(self._session, current_user.tenant_id)
        rows = await repo.acciones_por_dia(
            from_date=from_date,
            to_date=to_date,
            materia_ids=materia_ids,
        )
        total_acciones = sum(r.cantidad for r in rows)
        return AccionesXDiaResponse(
            items=[AccionXDia(fecha=r.fecha, cantidad=r.cantidad) for r in rows],
            total_acciones=total_acciones,
        )

    # ── F9.1(b) — estado de comunicaciones por docente ────────────────────────

    async def get_comunicaciones_docente(
        self,
        *,
        current_user: CurrentUser,
        scope: str | None,
        from_date=None,
        to_date=None,
    ) -> ComunicacionesDocenteResponse:
        effective_scope = scope or "all"
        materia_ids = await self._get_materia_ids_scoped(
            actor_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            scope=effective_scope,
        )
        com_repo = ComunicacionRepository(self._session, str(current_user.tenant_id))
        rows = await com_repo.estado_por_docente(materia_ids=materia_ids)

        unique_ids = {r.enviado_por for r in rows}
        user_map = await self._resolve_users(unique_ids, current_user.tenant_id)

        per_actor: dict[UUID, dict] = {}
        for row in rows:
            uid = row.enviado_por
            if uid not in user_map:
                continue
            if uid not in per_actor:
                per_actor[uid] = {
                    "actor_id": uid,
                    "nombre": user_map[uid]["nombre"],
                    "apellidos": user_map[uid]["apellidos"],
                    "estados": {},
                    "total": 0,
                }
            per_actor[uid]["estados"][row.estado] = row.cantidad
            per_actor[uid]["total"] += row.cantidad

        items = [EstadoComunicacionXDocente(**d) for d in per_actor.values()]
        return ComunicacionesDocenteResponse(items=items)

    # ── F9.1(c) — interacciones por docente y materia ────────────────────────

    async def get_interacciones(
        self,
        *,
        current_user: CurrentUser,
        scope: str | None,
        from_date=None,
        to_date=None,
        actor_id: UUID | None = None,
        accion: str | None = None,
    ) -> InteraccionesResponse:
        effective_scope = scope or "all"
        materia_ids = await self._get_materia_ids_scoped(
            actor_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            scope=effective_scope,
        )
        repo = AuditoriaRepository(self._session, current_user.tenant_id)
        rows = await repo.interacciones_por_docente_materia(
            from_date=from_date,
            to_date=to_date,
            actor_id_filter=actor_id,
            accion_filter=accion,
            materia_ids=materia_ids,
        )
        unique_ids = {r.actor_id for r in rows}
        user_map = await self._resolve_users(unique_ids, current_user.tenant_id)

        items = [
            InteraccionXDocenteMateria(
                actor_id=r.actor_id,
                nombre=user_map.get(r.actor_id, {}).get("nombre"),
                apellidos=user_map.get(r.actor_id, {}).get("apellidos"),
                materia_id=r.materia_id,
                accion=r.accion,
                cantidad=r.cantidad,
            )
            for r in rows
        ]
        return InteraccionesResponse(items=items)

    # ── F9.1(d) — últimas acciones ────────────────────────────────────────────

    async def get_ultimas_acciones(
        self,
        *,
        current_user: CurrentUser,
        scope: str | None,
        limit: int = 200,
        from_date=None,
        to_date=None,
        actor_id: UUID | None = None,
    ) -> UltimasAccionesResponse:
        effective_scope = scope or "all"
        materia_ids = await self._get_materia_ids_scoped(
            actor_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            scope=effective_scope,
        )
        repo = AuditoriaRepository(self._session, current_user.tenant_id)
        entries = await repo.ultimas_acciones(
            limit=limit,
            from_date=from_date,
            to_date=to_date,
            actor_id_filter=actor_id,
            materia_ids=materia_ids,
        )
        unique_ids = {e.actor_id for e in entries}
        user_map = await self._resolve_users(unique_ids, current_user.tenant_id)

        is_full = effective_scope == "all"
        items: list[AuditLogPublicEntry | AuditLogFullEntry] = []
        for e in entries:
            user_info = user_map.get(e.actor_id, {})
            if is_full:
                items.append(AuditLogFullEntry(
                    id=e.id,
                    fecha_hora=e.fecha_hora,
                    actor_id=e.actor_id,
                    nombre_actor=user_info.get("nombre"),
                    apellidos_actor=user_info.get("apellidos"),
                    impersonado_id=e.impersonado_id,
                    materia_id=e.materia_id,
                    accion=e.accion,
                    detalle=e.detalle,
                    filas_afectadas=e.filas_afectadas,
                    ip=e.ip,
                    user_agent=e.user_agent,
                ))
            else:
                items.append(AuditLogPublicEntry(
                    id=e.id,
                    fecha_hora=e.fecha_hora,
                    actor_id=e.actor_id,
                    nombre_actor=user_info.get("nombre"),
                    apellidos_actor=user_info.get("apellidos"),
                    impersonado_id=e.impersonado_id,
                    materia_id=e.materia_id,
                    accion=e.accion,
                    filas_afectadas=e.filas_afectadas,
                ))
        return UltimasAccionesResponse(items=items, limit_aplicado=limit)

    # ── F9.2 — log completo paginado ─────────────────────────────────────────

    async def get_log_completo(
        self,
        *,
        current_user: CurrentUser,
        scope: str | None,
        from_date=None,
        to_date=None,
        actor_id: UUID | None = None,
        accion: str | None = None,
        materia_id: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> PaginatedAuditLogResponse:
        effective_scope = scope or "all"
        materia_ids = await self._get_materia_ids_scoped(
            actor_id=current_user.user_id,
            tenant_id=current_user.tenant_id,
            scope=effective_scope,
        )
        # For scope=all, allow explicit materia_id filter; scope=own ignores it
        if effective_scope == "all" and materia_id is not None:
            materia_ids = {materia_id}

        repo = AuditoriaRepository(self._session, current_user.tenant_id)
        entries, total = await repo.log_completo(
            from_date=from_date,
            to_date=to_date,
            actor_id_filter=actor_id,
            accion_filter=accion,
            materia_ids=materia_ids,
            page=page,
            page_size=page_size,
        )
        unique_ids = {e.actor_id for e in entries}
        user_map = await self._resolve_users(unique_ids, current_user.tenant_id)

        is_full = effective_scope == "all"
        items: list[AuditLogPublicEntry | AuditLogFullEntry] = []
        for e in entries:
            user_info = user_map.get(e.actor_id, {})
            if is_full:
                items.append(AuditLogFullEntry(
                    id=e.id,
                    fecha_hora=e.fecha_hora,
                    actor_id=e.actor_id,
                    nombre_actor=user_info.get("nombre"),
                    apellidos_actor=user_info.get("apellidos"),
                    impersonado_id=e.impersonado_id,
                    materia_id=e.materia_id,
                    accion=e.accion,
                    detalle=e.detalle,
                    filas_afectadas=e.filas_afectadas,
                    ip=e.ip,
                    user_agent=e.user_agent,
                ))
            else:
                items.append(AuditLogPublicEntry(
                    id=e.id,
                    fecha_hora=e.fecha_hora,
                    actor_id=e.actor_id,
                    nombre_actor=user_info.get("nombre"),
                    apellidos_actor=user_info.get("apellidos"),
                    impersonado_id=e.impersonado_id,
                    materia_id=e.materia_id,
                    accion=e.accion,
                    filas_afectadas=e.filas_afectadas,
                ))

        pages = math.ceil(total / page_size) if total > 0 else 0
        return PaginatedAuditLogResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
