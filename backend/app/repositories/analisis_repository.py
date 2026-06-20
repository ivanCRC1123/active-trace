"""AnalisisRepository — complex read queries for C-11 analisis-atrasados-reportes.

All SQL lives here. Services only orchestrate; they never write SQL.
Queries implement RN-06 (atrasados), RN-09 (ranking), D-C11-3 (faltantes),
D-C11-4 (atrasado union), D-C11-6 (pct_actividades_aprobadas).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calificacion import Calificacion
from app.models.entrada_padron import EntradaPadron
from app.models.finalizacion_actividad import FinalizacionActividad
from app.models.version_padron import VersionPadron


class AtrasadoRow(TypedDict):
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    regional: str | None
    actividades_faltantes: list[str]
    actividades_bajo_umbral: list[str]


class RankingRow(TypedDict):
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    total_aprobadas: int
    total_calificaciones: int


class NotaFinalRow(TypedDict):
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    aprobadas: int
    total_calificaciones: int
    pct_actividades_aprobadas: float | None


@dataclass
class ReporteRapidoRow:
    total_alumnos: int = 0
    total_actividades: int = 0
    total_aprobaciones: int = 0
    total_desaprobaciones: int = 0
    alumnos_con_desaprobacion: int = 0
    alumnos_atrasados: int = 0
    tiene_datos: bool = False


@dataclass
class MonitorFilters:
    materia_id: UUID | None = None
    cohorte_id: UUID | None = None
    alumno: str | None = None
    comision: str | None = None
    regional: str | None = None
    estado: str | None = None       # "atrasado" | "al_dia" | None
    fecha_desde: str | None = None  # ISO date string YYYY-MM-DD
    fecha_hasta: str | None = None
    limit: int = 100
    offset: int = 0
    # scope: asignacion_ids of current user (None = all)
    asignacion_ids: list[UUID] = field(default_factory=list)


class MonitorRow(TypedDict):
    entrada_padron_id: UUID
    nombre: str
    apellidos: str
    comision: str | None
    regional: str | None
    materia_id: UUID
    cohorte_id: UUID
    estado: str
    actividades_faltantes: list[str]
    actividades_bajo_umbral: list[str]
    total_aprobadas: int
    total_calificaciones: int


class AnalisisRepository:
    """Read-only query repository for analisis endpoints.

    Does NOT extend BaseRepository (no tenant-scoped CRUD). Uses raw
    sa.text / ORM selects directly against the session.
    """

    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self._session = session
        self._tenant_id = UUID(tenant_id)

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _padron_activo(
        self, materia_id: UUID, cohorte_id: UUID
    ) -> list[dict]:
        """Return all active-padron students for a materia×cohorte."""
        stmt = (
            sa.select(
                EntradaPadron.id.label("ep_id"),
                EntradaPadron.nombre,
                EntradaPadron.apellidos,
                EntradaPadron.comision,
                EntradaPadron.regional,
            )
            .join(VersionPadron, EntradaPadron.version_id == VersionPadron.id)
            .where(
                VersionPadron.tenant_id == self._tenant_id,
                VersionPadron.materia_id == materia_id,
                VersionPadron.cohorte_id == cohorte_id,
                VersionPadron.activa.is_(True),
                VersionPadron.deleted_at.is_(None),
                EntradaPadron.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return [row._asdict() for row in result.all()]

    async def _actividades_scope(
        self, materia_id: UUID, asignacion_id: UUID | None
    ) -> list[str]:
        """Return distinct actividad names in scope."""
        where = [
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.materia_id == materia_id,
            Calificacion.deleted_at.is_(None),
        ]
        if asignacion_id is not None:
            where.append(Calificacion.asignacion_id == asignacion_id)

        stmt = sa.select(sa.distinct(Calificacion.actividad)).where(*where)
        result = await self._session.execute(stmt)
        return [r for r, in result.all()]

    async def _textual_actividades(
        self, materia_id: UUID, asignacion_id: UUID | None
    ) -> set[str]:
        """Return set of activity names that have at least one textual grade."""
        where = [
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.materia_id == materia_id,
            Calificacion.nota_textual.isnot(None),
            Calificacion.deleted_at.is_(None),
        ]
        if asignacion_id is not None:
            where.append(Calificacion.asignacion_id == asignacion_id)
        stmt = sa.select(sa.distinct(Calificacion.actividad)).where(*where)
        result = await self._session.execute(stmt)
        return {r for r, in result.all()}

    async def _calificaciones_by_ep(
        self,
        materia_id: UUID,
        asignacion_id: UUID | None,
        ep_ids: list[UUID],
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
    ) -> dict[UUID, list[dict]]:
        """Return calificaciones grouped by entrada_padron_id for ep_ids."""
        if not ep_ids:
            return {}
        where = [
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.materia_id == materia_id,
            Calificacion.entrada_padron_id.in_(ep_ids),
            Calificacion.deleted_at.is_(None),
        ]
        if asignacion_id is not None:
            where.append(Calificacion.asignacion_id == asignacion_id)
        if fecha_desde:
            where.append(Calificacion.importado_at >= sa.cast(fecha_desde, sa.Date))
        if fecha_hasta:
            where.append(Calificacion.importado_at <= sa.cast(fecha_hasta, sa.Date))

        stmt = sa.select(
            Calificacion.entrada_padron_id,
            Calificacion.actividad,
            Calificacion.aprobado,
        ).where(*where)
        result = await self._session.execute(stmt)

        grouped: dict[UUID, list[dict]] = {}
        for row in result.all():
            grouped.setdefault(row.entrada_padron_id, []).append(
                {"actividad": row.actividad, "aprobado": row.aprobado}
            )
        return grouped

    async def _finalizadas_by_ep(
        self,
        materia_id: UUID,
        asignacion_id: UUID | None,
        ep_ids: list[UUID],
    ) -> dict[UUID, set[str]]:
        """Return {ep_id: {actividad, ...}} for finalizado=True rows."""
        if not ep_ids:
            return {}
        where = [
            FinalizacionActividad.tenant_id == self._tenant_id,
            FinalizacionActividad.materia_id == materia_id,
            FinalizacionActividad.entrada_padron_id.in_(ep_ids),
            FinalizacionActividad.finalizado.is_(True),
            FinalizacionActividad.deleted_at.is_(None),
        ]
        if asignacion_id is not None:
            where.append(FinalizacionActividad.asignacion_id == asignacion_id)

        stmt = sa.select(
            FinalizacionActividad.entrada_padron_id,
            FinalizacionActividad.actividad,
        ).where(*where)
        result = await self._session.execute(stmt)

        grouped: dict[UUID, set[str]] = {}
        for row in result.all():
            grouped.setdefault(row.entrada_padron_id, set()).add(row.actividad)
        return grouped

    # ── Public queries ─────────────────────────────────────────────────────────

    async def atrasados(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        asignacion_id: UUID | None,
    ) -> list[AtrasadoRow]:
        """Compute atrasados per RN-06 + D-C11-3/D-C11-4.

        Faltante = no calificacion AND NOT (textual + finalizado).
        Bajo_umbral = aprobado=False.
        """
        padron = await self._padron_activo(materia_id, cohorte_id)
        if not padron:
            return []

        actividades = await self._actividades_scope(materia_id, asignacion_id)
        if not actividades:
            return []

        ep_ids = [p["ep_id"] for p in padron]
        cals = await self._calificaciones_by_ep(materia_id, asignacion_id, ep_ids)
        textual_acts = await self._textual_actividades(materia_id, asignacion_id)
        finalizadas = await self._finalizadas_by_ep(materia_id, asignacion_id, ep_ids)

        result: list[AtrasadoRow] = []
        for p in padron:
            ep_id = p["ep_id"]
            ep_cals = cals.get(ep_id, [])
            calificadas = {c["actividad"] for c in ep_cals}
            ep_finalizadas = finalizadas.get(ep_id, set())

            # Faltantes (D-C11-3): missing AND NOT sin-corregir
            faltantes = [
                act for act in actividades
                if act not in calificadas
                and not (act in textual_acts and act in ep_finalizadas)
            ]

            # Bajo umbral: has calificacion but aprobado=False
            bajo_umbral = [c["actividad"] for c in ep_cals if not c["aprobado"]]

            if faltantes or bajo_umbral:
                result.append(AtrasadoRow(
                    entrada_padron_id=ep_id,
                    nombre=p["nombre"],
                    apellidos=p["apellidos"],
                    comision=p["comision"],
                    regional=p["regional"],
                    actividades_faltantes=sorted(faltantes),
                    actividades_bajo_umbral=sorted(bajo_umbral),
                ))

        return result

    async def total_alumnos_padron(
        self, materia_id: UUID, cohorte_id: UUID
    ) -> int:
        """Count students in the active padron."""
        stmt = (
            sa.select(sa.func.count(EntradaPadron.id))
            .join(VersionPadron, EntradaPadron.version_id == VersionPadron.id)
            .where(
                VersionPadron.tenant_id == self._tenant_id,
                VersionPadron.materia_id == materia_id,
                VersionPadron.cohorte_id == cohorte_id,
                VersionPadron.activa.is_(True),
                VersionPadron.deleted_at.is_(None),
                EntradaPadron.deleted_at.is_(None),
            )
        )
        return (await self._session.execute(stmt)).scalar_one()

    async def ranking(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        asignacion_id: UUID | None,
    ) -> list[RankingRow]:
        """Ranking of students by count of approved activities (RN-09)."""
        padron = await self._padron_activo(materia_id, cohorte_id)
        if not padron:
            return []

        ep_ids = [p["ep_id"] for p in padron]
        cals = await self._calificaciones_by_ep(materia_id, asignacion_id, ep_ids)

        padron_map = {p["ep_id"]: p for p in padron}

        rows: list[tuple[int, RankingRow]] = []
        for ep_id, ep_cals in cals.items():
            total_aprobadas = sum(1 for c in ep_cals if c["aprobado"])
            if total_aprobadas == 0:
                continue  # RN-09: exclude students with 0 approved
            p = padron_map.get(ep_id)
            if p is None:
                continue
            rows.append((
                total_aprobadas,
                RankingRow(
                    entrada_padron_id=ep_id,
                    nombre=p["nombre"],
                    apellidos=p["apellidos"],
                    comision=p["comision"],
                    total_aprobadas=total_aprobadas,
                    total_calificaciones=len(ep_cals),
                ),
            ))

        rows.sort(key=lambda x: (-x[0], x[1]["apellidos"], x[1]["nombre"]))
        return [r for _, r in rows]

    async def notas_finales(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        asignacion_id: UUID | None,
    ) -> list[NotaFinalRow]:
        """% de actividades aprobadas per student (D-C11-6)."""
        padron = await self._padron_activo(materia_id, cohorte_id)
        if not padron:
            return []

        ep_ids = [p["ep_id"] for p in padron]
        cals = await self._calificaciones_by_ep(materia_id, asignacion_id, ep_ids)

        result: list[NotaFinalRow] = []
        for p in padron:
            ep_id = p["ep_id"]
            ep_cals = cals.get(ep_id, [])
            aprobadas = sum(1 for c in ep_cals if c["aprobado"])
            total = len(ep_cals)
            pct = round(aprobadas / total * 100, 2) if total > 0 else None
            result.append(NotaFinalRow(
                entrada_padron_id=ep_id,
                nombre=p["nombre"],
                apellidos=p["apellidos"],
                comision=p["comision"],
                aprobadas=aprobadas,
                total_calificaciones=total,
                pct_actividades_aprobadas=pct,
            ))

        result.sort(key=lambda r: (r["apellidos"], r["nombre"]))
        return result

    async def reporte_rapido(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        asignacion_id: UUID | None,
    ) -> ReporteRapidoRow:
        """Summary metrics for a materia×cohorte (F2.4)."""
        total_alumnos = await self.total_alumnos_padron(materia_id, cohorte_id)

        actividades = await self._actividades_scope(materia_id, asignacion_id)
        if not actividades:
            return ReporteRapidoRow(total_alumnos=total_alumnos)

        # Aggregate calificaciones
        where = [
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.materia_id == materia_id,
            Calificacion.deleted_at.is_(None),
        ]
        if asignacion_id is not None:
            where.append(Calificacion.asignacion_id == asignacion_id)

        stmt = sa.select(
            sa.func.count(Calificacion.id).label("total"),
            sa.func.count(Calificacion.id).filter(Calificacion.aprobado.is_(True)).label("aprobadas"),
            sa.func.count(Calificacion.id).filter(Calificacion.aprobado.is_(False)).label("desaprobadas"),
            sa.func.count(sa.distinct(Calificacion.entrada_padron_id)).filter(
                Calificacion.aprobado.is_(False)
            ).label("alumnos_desaprobados"),
        ).where(*where)

        row = (await self._session.execute(stmt)).one()
        atrasados = await self.atrasados(materia_id, cohorte_id, asignacion_id)

        return ReporteRapidoRow(
            total_alumnos=total_alumnos,
            total_actividades=len(actividades),
            total_aprobaciones=row.aprobadas or 0,
            total_desaprobaciones=row.desaprobadas or 0,
            alumnos_con_desaprobacion=row.alumnos_desaprobados or 0,
            alumnos_atrasados=len(atrasados),
            tiene_datos=True,
        )

    async def monitor(
        self,
        filters: MonitorFilters,
    ) -> tuple[list[MonitorRow], int]:
        """Unified monitor query (F2.7/F2.8/F2.9).

        Returns (items, total_unfiltered_count).
        Scope=own via filters.asignacion_ids (empty = scope=all).
        """
        # Build padron base query with optional filters
        padron_where = [
            VersionPadron.tenant_id == self._tenant_id,
            VersionPadron.activa.is_(True),
            VersionPadron.deleted_at.is_(None),
            EntradaPadron.deleted_at.is_(None),
        ]
        if filters.materia_id:
            padron_where.append(VersionPadron.materia_id == filters.materia_id)
        if filters.cohorte_id:
            padron_where.append(VersionPadron.cohorte_id == filters.cohorte_id)
        if filters.comision:
            padron_where.append(EntradaPadron.comision == filters.comision)
        if filters.regional:
            padron_where.append(EntradaPadron.regional == filters.regional)
        if filters.alumno:
            like = f"%{filters.alumno}%"
            padron_where.append(
                sa.or_(
                    EntradaPadron.nombre.ilike(like),
                    EntradaPadron.apellidos.ilike(like),
                )
            )

        stmt = (
            sa.select(
                EntradaPadron.id.label("ep_id"),
                EntradaPadron.nombre,
                EntradaPadron.apellidos,
                EntradaPadron.comision,
                EntradaPadron.regional,
                VersionPadron.materia_id,
                VersionPadron.cohorte_id,
            )
            .join(VersionPadron, EntradaPadron.version_id == VersionPadron.id)
            .where(*padron_where)
            .order_by(EntradaPadron.apellidos, EntradaPadron.nombre)
        )

        # scope=own: only students that have a calificacion from one of the user's asignaciones
        if filters.asignacion_ids:
            scoped_ep = (
                sa.select(Calificacion.entrada_padron_id)
                .where(
                    Calificacion.asignacion_id.in_(filters.asignacion_ids),
                    Calificacion.deleted_at.is_(None),
                )
                .scalar_subquery()
            )
            stmt = stmt.where(EntradaPadron.id.in_(scoped_ep))

        padron_result = await self._session.execute(stmt)
        all_padron = padron_result.all()
        total = len(all_padron)

        if not all_padron:
            return [], 0

        # Paginate
        paginated = all_padron[filters.offset: filters.offset + filters.limit]
        if not paginated:
            return [], total

        ep_ids = [row.ep_id for row in paginated]

        # Fetch calificaciones for paginated ep_ids
        # Use the materia_ids and asignacion_ids from filters
        materia_ids = {row.materia_id for row in paginated}
        asig_id = None if not filters.asignacion_ids else None  # scope=all if no asig filter

        # Build a mapping (ep_id, materia_id) → [calificaciones]
        cal_where = [
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.entrada_padron_id.in_(ep_ids),
            Calificacion.materia_id.in_(materia_ids),
            Calificacion.deleted_at.is_(None),
        ]
        if filters.asignacion_ids:
            cal_where.append(Calificacion.asignacion_id.in_(filters.asignacion_ids))
        if filters.fecha_desde:
            cal_where.append(Calificacion.importado_at >= sa.cast(filters.fecha_desde, sa.Date))
        if filters.fecha_hasta:
            cal_where.append(Calificacion.importado_at <= sa.cast(filters.fecha_hasta, sa.Date))

        cal_stmt = sa.select(
            Calificacion.entrada_padron_id,
            Calificacion.materia_id,
            Calificacion.actividad,
            Calificacion.aprobado,
        ).where(*cal_where)
        cal_result = await self._session.execute(cal_stmt)

        # {(ep_id, materia_id): [{"actividad": ..., "aprobado": ...}]}
        cals_map: dict[tuple, list[dict]] = {}
        for row in cal_result.all():
            key = (row.entrada_padron_id, row.materia_id)
            cals_map.setdefault(key, []).append(
                {"actividad": row.actividad, "aprobado": row.aprobado}
            )

        # Fetch actividades per materia
        act_where = [
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.materia_id.in_(materia_ids),
            Calificacion.deleted_at.is_(None),
        ]
        if filters.asignacion_ids:
            act_where.append(Calificacion.asignacion_id.in_(filters.asignacion_ids))

        act_stmt = (
            sa.select(Calificacion.materia_id, Calificacion.actividad)
            .where(*act_where)
            .distinct()
        )
        act_result = await self._session.execute(act_stmt)
        actividades_by_materia: dict[UUID, list[str]] = {}
        for row in act_result.all():
            actividades_by_materia.setdefault(row.materia_id, []).append(row.actividad)

        # Fetch textual actividades per materia
        textual_where = [
            Calificacion.tenant_id == self._tenant_id,
            Calificacion.materia_id.in_(materia_ids),
            Calificacion.nota_textual.isnot(None),
            Calificacion.deleted_at.is_(None),
        ]
        if filters.asignacion_ids:
            textual_where.append(Calificacion.asignacion_id.in_(filters.asignacion_ids))

        textual_stmt = (
            sa.select(Calificacion.materia_id, Calificacion.actividad)
            .where(*textual_where)
            .distinct()
        )
        textual_result = await self._session.execute(textual_stmt)
        textual_by_materia: dict[UUID, set[str]] = {}
        for row in textual_result.all():
            textual_by_materia.setdefault(row.materia_id, set()).add(row.actividad)

        # Fetch finalizaciones
        fin_where = [
            FinalizacionActividad.tenant_id == self._tenant_id,
            FinalizacionActividad.entrada_padron_id.in_(ep_ids),
            FinalizacionActividad.materia_id.in_(materia_ids),
            FinalizacionActividad.finalizado.is_(True),
            FinalizacionActividad.deleted_at.is_(None),
        ]
        if filters.asignacion_ids:
            fin_where.append(FinalizacionActividad.asignacion_id.in_(filters.asignacion_ids))

        fin_stmt = sa.select(
            FinalizacionActividad.entrada_padron_id,
            FinalizacionActividad.materia_id,
            FinalizacionActividad.actividad,
        ).where(*fin_where)
        fin_result = await self._session.execute(fin_stmt)
        finalizadas_map: dict[tuple, set[str]] = {}
        for row in fin_result.all():
            key = (row.entrada_padron_id, row.materia_id)
            finalizadas_map.setdefault(key, set()).add(row.actividad)

        # Build monitor items
        items: list[MonitorRow] = []
        for p in paginated:
            key = (p.ep_id, p.materia_id)
            ep_cals = cals_map.get(key, [])
            calificadas = {c["actividad"] for c in ep_cals}
            textual_acts = textual_by_materia.get(p.materia_id, set())
            ep_finalizadas = finalizadas_map.get(key, set())
            actividades = actividades_by_materia.get(p.materia_id, [])

            faltantes = [
                act for act in actividades
                if act not in calificadas
                and not (act in textual_acts and act in ep_finalizadas)
            ]
            bajo_umbral = [c["actividad"] for c in ep_cals if not c["aprobado"]]
            total_aprobadas = sum(1 for c in ep_cals if c["aprobado"])
            estado = "atrasado" if (faltantes or bajo_umbral) else "al_dia"

            if filters.estado and filters.estado != estado:
                continue

            items.append(MonitorRow(
                entrada_padron_id=p.ep_id,
                nombre=p.nombre,
                apellidos=p.apellidos,
                comision=p.comision,
                regional=p.regional,
                materia_id=p.materia_id,
                cohorte_id=p.cohorte_id,
                estado=estado,
                actividades_faltantes=sorted(faltantes),
                actividades_bajo_umbral=sorted(bajo_umbral),
                total_aprobadas=total_aprobadas,
                total_calificaciones=len(ep_cals),
            ))

        return items, total
