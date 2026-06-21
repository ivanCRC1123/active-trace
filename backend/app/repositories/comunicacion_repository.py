"""ComunicacionRepository — C-12 comunicaciones-cola-worker.

Responsabilidades:
- CRUD de Comunicacion con scope de tenant.
- Validación de la FSM antes de cada transición de estado (RN-15).
- Queries para worker (cross-tenant, ENVIANDO) y para API (scoped).

No hay lógica de negocio aquí. Todo SQL vive aquí, nunca en Services.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comunicacion import (
    Comunicacion,
    EstadoComunicacion,
    validar_transicion,
)


@dataclass(frozen=True)
class EstadoDocenteRow:
    enviado_por: UUID
    estado: str
    cantidad: int


class ComunicacionRepository:
    """Repository scoped a un tenant.

    Para queries cross-tenant del worker usa ComunicacionRepository._worker_query.
    """

    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = tenant_id

    # ── Escritura ─────────────────────────────────────────────────────────────

    async def bulk_create(self, rows: list[dict]) -> list[Comunicacion]:
        """Inserta N comunicaciones en el mismo lote. tenant_id se inyecta aquí."""
        objs = []
        for row in rows:
            obj = Comunicacion(**row, tenant_id=UUID(self._tenant_id))
            self._session.add(obj)
            objs.append(obj)
        await self._session.flush()
        for obj in objs:
            await self._session.refresh(obj)
        return objs

    async def set_estado(
        self,
        com_id: UUID,
        nuevo_estado: EstadoComunicacion,
        *,
        aprobado_por: UUID | None = None,
        enviado_at: datetime | None = None,
    ) -> Comunicacion:
        """Transiciona el estado de una Comunicacion validando la FSM.

        Raises ValueError si la transición no está permitida.
        """
        obj = await self._get_by_id_scoped(com_id)
        if obj is None:
            raise ValueError("comunicacion_not_found")
        validar_transicion(obj.estado, nuevo_estado.value)

        obj.estado = nuevo_estado.value
        if aprobado_por is not None:
            obj.aprobado_por = aprobado_por
            obj.aprobado_at = datetime.now(tz=timezone.utc)
        if enviado_at is not None:
            obj.enviado_at = enviado_at

        await self._session.flush()
        await self._session.refresh(obj)
        return obj

    async def aprobar_lote(
        self, lote_id: UUID, aprobado_por: UUID
    ) -> tuple[int, int]:
        """Transiciona todos los PENDIENTE del lote → ENVIANDO.

        Retorna (aprobadas, ignoradas) — ignoradas son las que ya no estaban
        en PENDIENTE (ya enviadas, canceladas, etc.).
        """
        pendientes = await self._list_lote_en_estado(
            lote_id, EstadoComunicacion.PENDIENTE
        )
        aprobadas = 0
        ignoradas = 0
        now = datetime.now(tz=timezone.utc)
        for com in pendientes:
            com.estado = EstadoComunicacion.ENVIANDO.value
            com.aprobado_por = aprobado_por
            com.aprobado_at = now
            aprobadas += 1
        total_lote = await self._count_lote(lote_id)
        ignoradas = total_lote - aprobadas
        await self._session.flush()
        return aprobadas, ignoradas

    async def cancelar_lote(self, lote_id: UUID) -> int:
        """Cancela todos los PENDIENTE del lote. Retorna cantidad cancelada."""
        pendientes = await self._list_lote_en_estado(
            lote_id, EstadoComunicacion.PENDIENTE
        )
        for com in pendientes:
            com.estado = EstadoComunicacion.CANCELADO.value
        await self._session.flush()
        return len(pendientes)

    # ── Lectura ───────────────────────────────────────────────────────────────

    async def get_by_id(self, com_id: UUID) -> Comunicacion | None:
        return await self._get_by_id_scoped(com_id)

    async def list_by_lote(self, lote_id: UUID) -> list[Comunicacion]:
        stmt = (
            select(Comunicacion)
            .where(
                Comunicacion.tenant_id == UUID(self._tenant_id),
                Comunicacion.lote_id == lote_id,
                Comunicacion.deleted_at.is_(None),
            )
            .order_by(Comunicacion.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_usuario(
        self,
        usuario_id: UUID,
        *,
        lote_id: UUID | None = None,
        estado: str | None = None,
        materia_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Comunicacion], int]:
        """Lista comunicaciones del usuario (scope=own) con filtros opcionales."""
        base = (
            select(Comunicacion)
            .where(
                Comunicacion.tenant_id == UUID(self._tenant_id),
                Comunicacion.enviado_por == usuario_id,
                Comunicacion.deleted_at.is_(None),
            )
        )
        if lote_id is not None:
            base = base.where(Comunicacion.lote_id == lote_id)
        if estado is not None:
            base = base.where(Comunicacion.estado == estado)
        if materia_id is not None:
            base = base.where(Comunicacion.materia_id == materia_id)

        count_stmt = base.with_only_columns(  # type: ignore[call-overload]
            Comunicacion.id
        )
        count_result = await self._session.execute(count_stmt)
        total = len(count_result.all())

        stmt = base.order_by(Comunicacion.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def list_tenant(
        self,
        *,
        lote_id: UUID | None = None,
        estado: str | None = None,
        materia_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Comunicacion], int]:
        """Lista todas las comunicaciones del tenant (scope=all)."""
        base = (
            select(Comunicacion)
            .where(
                Comunicacion.tenant_id == UUID(self._tenant_id),
                Comunicacion.deleted_at.is_(None),
            )
        )
        if lote_id is not None:
            base = base.where(Comunicacion.lote_id == lote_id)
        if estado is not None:
            base = base.where(Comunicacion.estado == estado)
        if materia_id is not None:
            base = base.where(Comunicacion.materia_id == materia_id)

        count_stmt = base.with_only_columns(Comunicacion.id)  # type: ignore[call-overload]
        count_result = await self._session.execute(count_stmt)
        total = len(count_result.all())

        stmt = base.order_by(Comunicacion.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    def resumen_estados(self, comunicaciones: list[Comunicacion]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for com in comunicaciones:
            counts[com.estado] += 1
        return dict(counts)

    # ── C-19 — panel queries ──────────────────────────────────────────────────

    async def estado_por_docente(
        self,
        *,
        materia_ids: set[UUID] | None = None,
    ) -> list["EstadoDocenteRow"]:
        """Agrupa comunicaciones por (enviado_por, estado) para el panel F9.1(b).

        materia_ids=None → sin filtro de materia (scope=all).
        materia_ids=set() → resultado vacío inmediato (COORDINADOR sin materias).
        """
        if materia_ids is not None and len(materia_ids) == 0:
            return []

        stmt = (
            select(
                Comunicacion.enviado_por,
                Comunicacion.estado,
                func.count().label("cantidad"),
            )
            .where(
                Comunicacion.tenant_id == UUID(self._tenant_id),
                Comunicacion.deleted_at.is_(None),
            )
        )
        if materia_ids is not None:
            stmt = stmt.where(Comunicacion.materia_id.in_(materia_ids))

        stmt = stmt.group_by(Comunicacion.enviado_por, Comunicacion.estado)
        rows = (await self._session.execute(stmt)).all()
        return [
            EstadoDocenteRow(enviado_por=r.enviado_por, estado=r.estado, cantidad=r.cantidad)
            for r in rows
        ]

    # ── Worker (cross-tenant) ─────────────────────────────────────────────────

    @staticmethod
    async def list_enviando_all_tenants(
        session: AsyncSession, limit: int = 100
    ) -> list[Comunicacion]:
        """Query cross-tenant para el worker de despacho.

        Solo el worker llama este método — nunca un usuario autenticado.
        Retorna comunicaciones en estado ENVIANDO que no están soft-deleted.
        """
        stmt = (
            select(Comunicacion)
            .where(
                Comunicacion.estado == EstadoComunicacion.ENVIANDO.value,
                Comunicacion.deleted_at.is_(None),
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def set_estado_worker(
        session: AsyncSession,
        com: Comunicacion,
        nuevo_estado: EstadoComunicacion,
        enviado_at: datetime | None = None,
    ) -> None:
        """Transiciona estado desde el worker (sin scope de tenant)."""
        validar_transicion(com.estado, nuevo_estado.value)
        com.estado = nuevo_estado.value
        if enviado_at is not None:
            com.enviado_at = enviado_at
        await session.flush()

    # ── Helpers privados ──────────────────────────────────────────────────────

    async def _get_by_id_scoped(self, com_id: UUID) -> Comunicacion | None:
        stmt = select(Comunicacion).where(
            Comunicacion.id == com_id,
            Comunicacion.tenant_id == UUID(self._tenant_id),
            Comunicacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _list_lote_en_estado(
        self, lote_id: UUID, estado: EstadoComunicacion
    ) -> list[Comunicacion]:
        stmt = select(Comunicacion).where(
            Comunicacion.tenant_id == UUID(self._tenant_id),
            Comunicacion.lote_id == lote_id,
            Comunicacion.estado == estado.value,
            Comunicacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _count_lote(self, lote_id: UUID) -> int:
        stmt = select(Comunicacion).where(
            Comunicacion.tenant_id == UUID(self._tenant_id),
            Comunicacion.lote_id == lote_id,
            Comunicacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
