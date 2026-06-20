"""ColoquiosService — business logic for C-14 evaluaciones-y-coloquios.

Error convention (ValueError messages → HTTP codes in router):
  "not found"                 → 404
  "evaluacion not found"      → 404
  "materia not found"         → 404
  "cohorte not found"         → 404
  "evaluacion already exists" → 409
  "sin_cupo"                  → 409  (cupo agotado)
  "reserva_already_active"    → 409  (alumno ya tiene reserva activa)
  "reserva not found"         → 404
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import RESULTADO_REGISTRAR
from app.models.evaluacion import (
    EstadoReserva,
    Evaluacion,
    ResultadoEvaluacion,
)
from app.repositories.cohorte_repository import CohorteRepository
from app.repositories.evaluacion_repository import (
    ConvocadoRepository,
    EvaluacionRepository,
    ReservaRepository,
    ResultadoRepository,
)
from app.repositories.materia_repository import MateriaRepository
from app.schemas.auth import CurrentUser
from app.schemas.coloquios import (
    ConvocadoImportRequest,
    EvaluacionCreate,
    EvaluacionUpdate,
    MetricasConvocatoria,
    MetricasPanel,
)
from app.services.audit_service import AuditService


class ColoquiosService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── FK validators ──────────────────────────────────────────────────────

    async def _get_materia(self, materia_id: UUID, tenant_id: UUID):
        repo = MateriaRepository(self._session, tenant_id)
        obj = await repo.get_by_id(materia_id)
        if obj is None:
            raise ValueError("materia not found")
        return obj

    async def _get_cohorte(self, cohorte_id: UUID, tenant_id: UUID):
        repo = CohorteRepository(self._session, tenant_id)
        obj = await repo.get_by_id(cohorte_id)
        if obj is None:
            raise ValueError("cohorte not found")
        return obj

    # ── Convocatoria CRUD ──────────────────────────────────────────────────

    async def create_convocatoria(
        self, *, tenant_id: UUID, data: EvaluacionCreate
    ) -> Evaluacion:
        await self._get_materia(data.materia_id, tenant_id)
        await self._get_cohorte(data.cohorte_id, tenant_id)
        repo = EvaluacionRepository(self._session, tenant_id)
        existing = await repo.get_by_instancia(
            data.materia_id, data.cohorte_id, data.tipo, data.instancia
        )
        if existing is not None:
            raise ValueError("evaluacion already exists")
        return await repo.create(
            {
                "materia_id": data.materia_id,
                "cohorte_id": data.cohorte_id,
                "tipo": data.tipo,
                "instancia": data.instancia,
                "dias_disponibles": data.dias_disponibles,
                "cupo_total": data.cupo_total,
            }
        )

    async def list_convocatorias(
        self,
        *,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        cohorte_id: UUID | None = None,
    ) -> list[Evaluacion]:
        repo = EvaluacionRepository(self._session, tenant_id)
        if materia_id is not None and cohorte_id is not None:
            return await repo.list_by_materia_cohorte(materia_id, cohorte_id)
        return list(await repo.list())

    async def get_convocatoria(self, *, id: UUID, tenant_id: UUID) -> Evaluacion:
        repo = EvaluacionRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return obj

    async def update_convocatoria(
        self, *, id: UUID, tenant_id: UUID, data: EvaluacionUpdate
    ) -> Evaluacion:
        repo = EvaluacionRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return obj
        return await repo.update(id, updates)

    async def delete_convocatoria(self, *, id: UUID, tenant_id: UUID) -> bool:
        repo = EvaluacionRepository(self._session, tenant_id)
        deleted = await repo.soft_delete(id)
        if not deleted:
            raise ValueError("not found")
        return True

    # ── Convocados ─────────────────────────────────────────────────────────

    async def importar_convocados(
        self,
        *,
        tenant_id: UUID,
        evaluacion_id: UUID,
        payload: ConvocadoImportRequest,
    ) -> int:
        repo = EvaluacionRepository(self._session, tenant_id)
        ev = await repo.get_by_id(evaluacion_id)
        if ev is None:
            raise ValueError("evaluacion not found")

        conv_repo = ConvocadoRepository(self._session, tenant_id)
        filas = [fila.model_dump() for fila in payload.filas]
        return await conv_repo.bulk_create(tenant_id, evaluacion_id, filas)

    # ── Métricas ────────────────────────────────────────────────────────────

    async def metricas_panel(self, *, tenant_id: UUID) -> MetricasPanel:
        repo = EvaluacionRepository(self._session, tenant_id)
        return MetricasPanel(
            total_alumnos_cargados=await repo.count_all_convocados(),
            instancias_activas=await repo.count_all_instancias(),
            reservas_activas=await repo.count_all_reservas_activas(),
            notas_registradas=await repo.count_all_resultados(),
        )

    async def metricas_convocatoria(
        self, *, tenant_id: UUID, evaluacion_id: UUID
    ) -> MetricasConvocatoria:
        ev_repo = EvaluacionRepository(self._session, tenant_id)
        ev = await ev_repo.get_by_id(evaluacion_id)
        if ev is None:
            raise ValueError("evaluacion not found")

        convocados = await ev_repo.count_convocados(evaluacion_id)
        reservas = await ev_repo.count_reservas_activas(evaluacion_id)
        resultados = await ev_repo.count_resultados(evaluacion_id)
        cupos_libres = -1 if ev.cupo_total == 0 else max(0, ev.cupo_total - reservas)

        return MetricasConvocatoria(
            evaluacion_id=evaluacion_id,
            convocados=convocados,
            reservas_activas=reservas,
            cupos_libres=cupos_libres,
            notas_registradas=resultados,
        )

    # ── Reservas ────────────────────────────────────────────────────────────

    async def reservar_turno(
        self,
        *,
        tenant_id: UUID,
        alumno_id: UUID,
        evaluacion_id: UUID,
        fecha_hora: datetime,
    ):
        # SELECT FOR UPDATE to protect cupo against concurrent inserts
        stmt = (
            select(Evaluacion)
            .where(
                Evaluacion.tenant_id == tenant_id,
                Evaluacion.id == evaluacion_id,
                Evaluacion.deleted_at.is_(None),
            )
            .with_for_update()
        )
        result = await self._session.execute(stmt)
        ev = result.scalar_one_or_none()
        if ev is None:
            raise ValueError("evaluacion not found")

        res_repo = ReservaRepository(self._session, tenant_id)

        existing = await res_repo.get_activa_by_alumno(evaluacion_id, alumno_id)
        if existing is not None:
            raise ValueError("reserva_already_active")

        if ev.cupo_total > 0:
            ocupados = await res_repo.count_activas(evaluacion_id)
            if ocupados >= ev.cupo_total:
                raise ValueError("sin_cupo")

        return await res_repo.create(
            {
                "evaluacion_id": evaluacion_id,
                "alumno_id": alumno_id,
                "fecha_hora": fecha_hora,
                "estado": EstadoReserva.Activa,
            }
        )

    async def cancelar_reserva(
        self,
        *,
        tenant_id: UUID,
        alumno_id: UUID,
        evaluacion_id: UUID,
        reserva_id: UUID,
    ):
        res_repo = ReservaRepository(self._session, tenant_id)
        reserva = await res_repo.get_activa_by_alumno(evaluacion_id, alumno_id)
        if reserva is None or reserva.id != reserva_id:
            raise ValueError("reserva not found")
        reserva.estado = EstadoReserva.Cancelada
        await self._session.flush()
        return reserva

    # ── Resultados ──────────────────────────────────────────────────────────

    async def registrar_resultado(
        self,
        *,
        tenant_id: UUID,
        evaluacion_id: UUID,
        alumno_id: UUID,
        nota_final: str,
        current_user: CurrentUser,
    ) -> ResultadoEvaluacion:
        ev_repo = EvaluacionRepository(self._session, tenant_id)
        ev = await ev_repo.get_by_id(evaluacion_id)
        if ev is None:
            raise ValueError("evaluacion not found")

        res_repo = ResultadoRepository(self._session, tenant_id)
        existing = await res_repo.get_by_alumno(evaluacion_id, alumno_id)

        if existing is None:
            resultado = await res_repo.create(
                {
                    "evaluacion_id": evaluacion_id,
                    "alumno_id": alumno_id,
                    "nota_final": nota_final,
                }
            )
            await AuditService(self._session).log(
                current_user=current_user,
                accion=RESULTADO_REGISTRAR,
                detalle={
                    "evaluacion_id": str(evaluacion_id),
                    "alumno_id": str(alumno_id),
                    "nota_anterior": None,
                    "nota_nueva": nota_final,
                },
            )
            return resultado

        nota_anterior = existing.nota_final
        existing.nota_final = nota_final
        existing.updated_at = datetime.utcnow()  # noqa: DTZ003 — column is TIMESTAMP WITHOUT TZ
        await self._session.flush()
        await AuditService(self._session).log(
            current_user=current_user,
            accion=RESULTADO_REGISTRAR,
            detalle={
                "evaluacion_id": str(evaluacion_id),
                "alumno_id": str(alumno_id),
                "nota_anterior": nota_anterior,
                "nota_nueva": nota_final,
            },
        )
        return existing

    async def list_resultados(
        self, *, tenant_id: UUID, evaluacion_id: UUID
    ) -> list[ResultadoEvaluacion]:
        ev_repo = EvaluacionRepository(self._session, tenant_id)
        if await ev_repo.get_by_id(evaluacion_id) is None:
            raise ValueError("evaluacion not found")
        res_repo = ResultadoRepository(self._session, tenant_id)
        return await res_repo.list_by_evaluacion(evaluacion_id)

    async def list_reservas(self, *, tenant_id: UUID, evaluacion_id: UUID):
        ev_repo = EvaluacionRepository(self._session, tenant_id)
        if await ev_repo.get_by_id(evaluacion_id) is None:
            raise ValueError("evaluacion not found")
        res_repo = ReservaRepository(self._session, tenant_id)
        return await res_repo.list_activas_by_evaluacion(evaluacion_id)
