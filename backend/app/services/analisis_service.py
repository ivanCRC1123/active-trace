"""AnalisisService — orchestration for C-11 analisis-atrasados-reportes.

No SQL here. All queries go through AnalisisRepository / FinalizacionRepository.
"""

from __future__ import annotations

import csv
import io
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.encryption import hmac_email
from app.models.asignacion import Asignacion
from app.models.entrada_padron import EntradaPadron
from app.models.version_padron import VersionPadron
from app.repositories.analisis_repository import AnalisisRepository, MonitorFilters
from app.repositories.finalizacion_repository import FinalizacionRepository
from app.schemas.analisis import (
    AlumnoAtrasado,
    AtrasadosResponse,
    EntregaSinCorregir,
    FinalizacionImportResult,
    MonitorItem,
    MonitorResponse,
    NotaFinalAlumno,
    NotasFinalesResponse,
    RankingItem,
    RankingResponse,
    ReporteRapidoResponse,
    SinCorregirResponse,
)
from app.schemas.auth import CurrentUser
from app.services.finalizacion_parser import parse_finalizacion_file
from sqlalchemy import select


class AnalisisService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _repo(self, tenant_id: str) -> AnalisisRepository:
        return AnalisisRepository(self._session, tenant_id)

    def _fin_repo(self, tenant_id: str) -> FinalizacionRepository:
        return FinalizacionRepository(self._session, tenant_id)

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _get_asignacion_activa(
        self, usuario_id: UUID, materia_id: UUID, cohorte_id: UUID, tenant_id: str
    ) -> Asignacion | None:
        stmt = select(Asignacion).where(
            Asignacion.tenant_id == UUID(tenant_id),
            Asignacion.usuario_id == usuario_id,
            Asignacion.materia_id == materia_id,
            Asignacion.cohorte_id == cohorte_id,
            Asignacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_asignaciones_activas(
        self, usuario_id: UUID, tenant_id: str
    ) -> list[UUID]:
        """Return all active asignacion IDs for a user (for scope=own monitor)."""
        stmt = select(Asignacion.id).where(
            Asignacion.tenant_id == UUID(tenant_id),
            Asignacion.usuario_id == usuario_id,
            Asignacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _resolve_padron_activo(
        self, tenant_id: str, materia_id: UUID, cohorte_id: UUID
    ) -> VersionPadron | None:
        stmt = select(VersionPadron).where(
            VersionPadron.tenant_id == UUID(tenant_id),
            VersionPadron.materia_id == materia_id,
            VersionPadron.cohorte_id == cohorte_id,
            VersionPadron.activa.is_(True),
            VersionPadron.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_ep_by_email_hash(
        self, email_hash: str, version_padron_id: UUID
    ) -> EntradaPadron | None:
        stmt = select(EntradaPadron).where(
            EntradaPadron.version_id == version_padron_id,
            EntradaPadron.email_hash == email_hash,
            EntradaPadron.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _asignacion_id_for_scope(
        self,
        current_user: CurrentUser,
        scope: str | None,
        materia_id: UUID,
        cohorte_id: UUID,
    ) -> UUID | None:
        """Return asignacion_id for scope=own, None for scope=all.

        Used by analisis queries that support cross-asignacion reads (atrasados, ranking,
        reporte_rapido, notas_finales, monitor). Returns None when scope=all so the
        repository omits the asignacion filter and reads across all asignaciones.
        """
        if scope == "all":
            return None
        asig = await self._get_asignacion_activa(
            current_user.user_id, materia_id, cohorte_id, str(current_user.tenant_id)
        )
        if asig is None:
            raise ValueError("asignacion_not_found")
        return asig.id

    async def _effective_asig_id(
        self,
        current_user: CurrentUser,
        materia_id: UUID,
        cohorte_id: UUID,
    ) -> UUID:
        """Always return a concrete asignacion_id for the calling user.

        Used by finalizacion import/query where we must scope to a single asignacion
        (the caller's own), regardless of whether they have scope=all permission.
        Raises ValueError('asignacion_not_found') if none exists.
        """
        asig = await self._get_asignacion_activa(
            current_user.user_id, materia_id, cohorte_id, str(current_user.tenant_id)
        )
        if asig is None:
            raise ValueError("asignacion_not_found")
        return asig.id

    # ── F1.2 — importar finalizacion ──────────────────────────────────────────

    async def importar_finalizacion(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        content: bytes,
        filename: str,
        scope: str | None,
    ) -> FinalizacionImportResult:
        tenant_id = str(current_user.tenant_id)
        version = await self._resolve_padron_activo(tenant_id, materia_id, cohorte_id)
        if version is None:
            raise ValueError("no_hay_padron_activo")

        # Always store finalizacion scoped to the caller's own asignacion (D-C11-2).
        # Even COORDINADOR (scope=all) must have an asignacion in the materia.
        effective_asig_id = await self._effective_asig_id(current_user, materia_id, cohorte_id)

        parsed = parse_finalizacion_file(
            content, filename,
            valores_completado=settings.FINALIZACION_VALORES_COMPLETADO,
        )

        fin_repo = self._fin_repo(tenant_id)
        await fin_repo.vaciar_por_asignacion_materia(effective_asig_id, materia_id)

        # Resolve email_hash → entrada_padron_id
        rows_to_insert: list[dict] = []
        no_vinculadas = 0
        finalizadas_count = 0

        for fila in parsed["filas"]:
            h = hmac_email(fila["email"])
            ep = await self._resolve_ep_by_email_hash(h, version.id)
            if ep is None:
                no_vinculadas += 1
                continue

            for actividad, finalizado in fila["actividades"].items():
                if finalizado:
                    finalizadas_count += 1
                rows_to_insert.append({
                    "entrada_padron_id": ep.id,
                    "materia_id": materia_id,
                    "asignacion_id": effective_asig_id,
                    "actividad": actividad,
                    "finalizado": finalizado,
                })

        await fin_repo.bulk_insert(rows_to_insert)

        # Count sin_corregir after import
        sin_corregir = await fin_repo.list_sin_corregir(materia_id, effective_asig_id)

        return FinalizacionImportResult(
            actividades_detectadas=len(parsed["actividades_detectadas"]),
            entradas_procesadas=len(parsed["filas"]),
            finalizadas=finalizadas_count,
            no_vinculadas=no_vinculadas,
            sin_corregir_count=len(sin_corregir),
            warnings=parsed["warnings"],
        )

    # ── F2.2 — atrasados ──────────────────────────────────────────────────────

    async def get_atrasados(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        scope: str | None,
    ) -> AtrasadosResponse:
        tenant_id = str(current_user.tenant_id)
        asig_id = await self._asignacion_id_for_scope(
            current_user, scope, materia_id, cohorte_id
        )
        repo = self._repo(tenant_id)
        atrasados = await repo.atrasados(materia_id, cohorte_id, asig_id)
        total = await repo.total_alumnos_padron(materia_id, cohorte_id)

        return AtrasadosResponse(
            total_alumnos=total,
            total_atrasados=len(atrasados),
            atrasados=[
                AlumnoAtrasado(
                    entrada_padron_id=r["entrada_padron_id"],
                    nombre=r["nombre"],
                    apellidos=r["apellidos"],
                    comision=r["comision"],
                    regional=r["regional"],
                    actividades_faltantes=r["actividades_faltantes"],
                    actividades_bajo_umbral=r["actividades_bajo_umbral"],
                )
                for r in atrasados
            ],
        )

    # ── F2.3 — ranking ────────────────────────────────────────────────────────

    async def get_ranking(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        scope: str | None,
    ) -> RankingResponse:
        tenant_id = str(current_user.tenant_id)
        asig_id = await self._asignacion_id_for_scope(
            current_user, scope, materia_id, cohorte_id
        )
        repo = self._repo(tenant_id)
        rows = await repo.ranking(materia_id, cohorte_id, asig_id)
        total_padron = await repo.total_alumnos_padron(materia_id, cohorte_id)

        items = [
            RankingItem(
                posicion=i + 1,
                entrada_padron_id=r["entrada_padron_id"],
                nombre=r["nombre"],
                apellidos=r["apellidos"],
                comision=r["comision"],
                total_aprobadas=r["total_aprobadas"],
                total_calificaciones=r["total_calificaciones"],
            )
            for i, r in enumerate(rows)
        ]
        return RankingResponse(
            items=items,
            total_incluidos=len(items),
            total_excluidos=total_padron - len(items),
        )

    # ── F2.4 — reporte rápido ─────────────────────────────────────────────────

    async def get_reporte_rapido(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        scope: str | None,
    ) -> ReporteRapidoResponse:
        tenant_id = str(current_user.tenant_id)
        asig_id = await self._asignacion_id_for_scope(
            current_user, scope, materia_id, cohorte_id
        )
        r = await self._repo(tenant_id).reporte_rapido(materia_id, cohorte_id, asig_id)
        return ReporteRapidoResponse(
            total_alumnos=r.total_alumnos,
            total_actividades=r.total_actividades,
            total_aprobaciones=r.total_aprobaciones,
            total_desaprobaciones=r.total_desaprobaciones,
            alumnos_con_desaprobacion=r.alumnos_con_desaprobacion,
            alumnos_atrasados=r.alumnos_atrasados,
            tiene_datos=r.tiene_datos,
        )

    # ── F2.5 — notas finales ──────────────────────────────────────────────────

    async def get_notas_finales(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        scope: str | None,
    ) -> NotasFinalesResponse:
        tenant_id = str(current_user.tenant_id)
        asig_id = await self._asignacion_id_for_scope(
            current_user, scope, materia_id, cohorte_id
        )
        rows = await self._repo(tenant_id).notas_finales(materia_id, cohorte_id, asig_id)
        return NotasFinalesResponse(
            items=[
                NotaFinalAlumno(
                    entrada_padron_id=r["entrada_padron_id"],
                    nombre=r["nombre"],
                    apellidos=r["apellidos"],
                    comision=r["comision"],
                    aprobadas=r["aprobadas"],
                    total_calificaciones=r["total_calificaciones"],
                    pct_actividades_aprobadas=r["pct_actividades_aprobadas"],
                )
                for r in rows
            ],
            total_alumnos=len(rows),
        )

    async def exportar_notas_finales(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        scope: str | None,
    ) -> str:
        response = await self.get_notas_finales(materia_id, cohorte_id, current_user, scope)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["apellidos", "nombre", "comision", "aprobadas", "total_actividades", "pct_actividades_aprobadas"])
        for item in response.items:
            pct_str = f"{item.pct_actividades_aprobadas:.2f}" if item.pct_actividades_aprobadas is not None else ""
            writer.writerow([
                item.apellidos, item.nombre, item.comision or "",
                item.aprobadas, item.total_calificaciones, pct_str,
            ])
        return buf.getvalue()

    # ── F2.6 — sin corregir ───────────────────────────────────────────────────

    async def get_sin_corregir(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        scope: str | None,
    ) -> SinCorregirResponse:
        tenant_id = str(current_user.tenant_id)
        # sin-corregir reads from the same asignacion-scoped finalizacion as the import.
        asig_id = await self._effective_asig_id(current_user, materia_id, cohorte_id)
        fin_repo = self._fin_repo(tenant_id)
        total_fin = await fin_repo.count_por_asignacion(asig_id, materia_id)
        aviso = None
        if total_fin == 0:
            aviso = "no_hay_finalizacion_importada"

        rows = await fin_repo.list_sin_corregir(materia_id, asig_id)
        return SinCorregirResponse(
            items=[
                EntregaSinCorregir(
                    entrada_padron_id=r["entrada_padron_id"],
                    nombre=r["nombre"],
                    apellidos=r["apellidos"],
                    comision=r["comision"],
                    actividad=r["actividad"],
                )
                for r in rows
            ],
            total=len(rows),
            aviso=aviso,
        )

    async def exportar_sin_corregir(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        scope: str | None,
    ) -> str:
        response = await self.get_sin_corregir(materia_id, cohorte_id, current_user, scope)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["apellidos", "nombre", "comision", "actividad"])
        for item in response.items:
            writer.writerow([item.apellidos, item.nombre, item.comision or "", item.actividad])
        return buf.getvalue()

    # ── F2.7/F2.8/F2.9 — monitor ─────────────────────────────────────────────

    async def get_monitor(
        self,
        current_user: CurrentUser,
        scope: str | None,
        materia_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        alumno: str | None = None,
        comision: str | None = None,
        regional: str | None = None,
        estado: str | None = None,
        fecha_desde: str | None = None,
        fecha_hasta: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> MonitorResponse:
        tenant_id = str(current_user.tenant_id)
        asignacion_ids: list[UUID] = []

        if scope != "all":
            # scope=own: restrict to current user's asignaciones
            asignacion_ids = await self._get_asignaciones_activas(current_user.user_id, tenant_id)

        filters = MonitorFilters(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            alumno=alumno,
            comision=comision,
            regional=regional,
            estado=estado,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            limit=limit,
            offset=offset,
            asignacion_ids=asignacion_ids,
        )

        items, total = await self._repo(tenant_id).monitor(filters)

        return MonitorResponse(
            items=[
                MonitorItem(
                    entrada_padron_id=r["entrada_padron_id"],
                    nombre=r["nombre"],
                    apellidos=r["apellidos"],
                    comision=r["comision"],
                    regional=r["regional"],
                    materia_id=r["materia_id"],
                    cohorte_id=r["cohorte_id"],
                    estado=r["estado"],
                    actividades_faltantes=r["actividades_faltantes"],
                    actividades_bajo_umbral=r["actividades_bajo_umbral"],
                    total_aprobadas=r["total_aprobadas"],
                    total_calificaciones=r["total_calificaciones"],
                )
                for r in items
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
