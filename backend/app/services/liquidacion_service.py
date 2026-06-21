"""LiquidacionService — calculation engine for C-18 (RN-34/35/36/37/38).

Formula (RN-34):
  total = monto_base + monto_plus
  monto_plus = Σ_grupo [ SalarioPlus(grupo, rol, periodo).monto × N_comisiones(docente, grupo) ]
  N_comisiones(docente, grupo) = Σ_asignacion len(comisiones) for active asignaciones
                                  where asignacion.materia is in that grupo

Exclusions:
  OD-5: no SalarioBase vigente → excluded, reported in sin_base_vigente
  RN-26: missing banco/cbu/alias_cbu → datos_bancarios_incompletos=True (computed, not excluded from calc)
  RN-35: facturador=True → excluido_por_factura=True (not included in cerrar batch)
  RN-36: NEXO → es_nexo=True, but included in total_sin_factura (KPI)

Immutability (RN-22/37):
  Any Cerrada in (cohorte, periodo) → recalcular rejected with 409.
  cerrar_batch: closes only Abierta + NOT incomplete + NOT facturador.
"""

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import LIQUIDACION_CERRAR
from app.models.base import LiquidacionEstado, RolLiquidable
from app.repositories.asignacion_repository import AsignacionRepository
from app.repositories.factura_repository import FacturaRepository
from app.repositories.liquidacion_repository import LiquidacionRepository
from app.repositories.materia_grupo_repository import MateriaGrupoRepository
from app.repositories.salario_base_repository import SalarioBaseRepository
from app.repositories.salario_plus_repository import SalarioPlusRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUser
from app.schemas.liquidaciones import (
    CalcularLiquidacionRequest,
    CalcularLiquidacionResponse,
    CerrarLiquidacionRequest,
    CerrarLiquidacionResponse,
    DocenteIncompletoInfo,
    KPIsLiquidacionResponse,
    LiquidacionResponse,
)
from app.services.audit_service import AuditService

_Q2 = Decimal("0.01")


def _periodo_to_dates(periodo: str) -> tuple[date, date]:
    """Parse 'YYYY-MM' into (first_day, last_day) of that month."""
    year, month = int(periodo[:4]), int(periodo[5:7])
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


class LiquidacionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _audit(self) -> AuditService:
        return AuditService(self._session)

    # ── Calcular ──────────────────────────────────────────────────────────────

    async def calcular(
        self, *, current_user: CurrentUser, data: CalcularLiquidacionRequest
    ) -> CalcularLiquidacionResponse:
        tid = current_user.tenant_id
        cohorte_id = data.cohorte_id
        periodo = data.periodo

        liq_repo = LiquidacionRepository(self._session, tid)

        # Immutability guard (RN-22/37)
        if await liq_repo.tiene_cerradas(cohorte_id, periodo):
            raise ValueError("periodo ya cerrado — recalculo no permitido")

        periodo_desde, periodo_hasta = _periodo_to_dates(periodo)
        periodo_date = periodo_desde  # first day of month for vigencia queries

        # Fetch active asignaciones for this cohorte × period
        asig_repo = AsignacionRepository(self._session, tid)
        asignaciones = await asig_repo.list_activas_en_cohorte_periodo(
            cohorte_id, periodo_desde, periodo_hasta
        )

        # Group by (usuario_id, RolLiquidable)
        groups: dict[tuple[UUID, RolLiquidable], list] = defaultdict(list)
        for a in asignaciones:
            try:
                rol_liq = RolLiquidable(a.rol_nombre)
            except ValueError:
                continue  # skip roles not in the liquidable enum
            groups[(a.usuario_id, rol_liq)].append(a)

        salario_base_repo = SalarioBaseRepository(self._session, tid)
        salario_plus_repo = SalarioPlusRepository(self._session, tid)
        materia_grupo_repo = MateriaGrupoRepository(self._session, tid)
        user_repo = UserRepository(self._session, tid)

        liquidaciones_result: list[LiquidacionResponse] = []
        sin_base_vigente: list[DocenteIncompletoInfo] = []
        sin_datos_bancarios: list[DocenteIncompletoInfo] = []

        for (usuario_id, rol), asigs in groups.items():
            # OD-5: require SalarioBase vigente
            base = await salario_base_repo.get_vigente(rol, periodo_date)
            if base is None:
                sin_base_vigente.append(
                    DocenteIncompletoInfo(
                        usuario_id=usuario_id, rol=rol, motivo="sin_base_vigente"
                    )
                )
                continue

            monto_base = base.monto

            # Fetch user for bancario + facturador
            user = await user_repo.get_by_id(usuario_id)
            datos_bancarios_incompletos = not all(
                [user.banco, user.cbu_cifrado, user.alias_cbu_cifrado]
            )
            excluido_por_factura = user.facturador

            # monto_plus: Σ_grupo SalarioPlus(grupo, rol, period) × N_comisiones
            grupo_comisiones: dict[str, int] = defaultdict(int)
            all_comisiones: list = []
            for a in asigs:
                comisiones = a.comisiones or []
                all_comisiones.extend(comisiones)
                if a.materia_id:
                    for mg in await materia_grupo_repo.list_by_materia(a.materia_id):
                        grupo_comisiones[mg.grupo] += len(comisiones)

            monto_plus = Decimal("0")
            for grupo, n in grupo_comisiones.items():
                plus = await salario_plus_repo.get_vigente(grupo, rol, periodo_date)
                if plus:
                    monto_plus += plus.monto * n

            monto_base = monto_base.quantize(_Q2)
            monto_plus = monto_plus.quantize(_Q2)
            total = (monto_base + monto_plus).quantize(_Q2)
            es_nexo = (rol == RolLiquidable.NEXO)

            row_data = dict(
                cohorte_id=cohorte_id,
                periodo=periodo,
                usuario_id=usuario_id,
                rol=rol,
                comisiones=all_comisiones,
                monto_base=monto_base,
                monto_plus=monto_plus,
                total=total,
                es_nexo=es_nexo,
                excluido_por_factura=excluido_por_factura,
                datos_bancarios_incompletos=datos_bancarios_incompletos,
            )

            existing = await liq_repo.get_by_docente_periodo(
                cohorte_id, usuario_id, rol, periodo
            )
            if existing:
                liq = await liq_repo.update(str(existing.id), row_data)
            else:
                liq = await liq_repo.create(row_data)

            liquidaciones_result.append(LiquidacionResponse.model_validate(liq))

            if datos_bancarios_incompletos and not excluido_por_factura:
                sin_datos_bancarios.append(
                    DocenteIncompletoInfo(
                        usuario_id=usuario_id,
                        rol=rol,
                        motivo="datos_bancarios_incompletos",
                    )
                )

        return CalcularLiquidacionResponse(
            liquidaciones=liquidaciones_result,
            sin_base_vigente=sin_base_vigente,
            sin_datos_bancarios=sin_datos_bancarios,
        )

    # ── Cerrar ────────────────────────────────────────────────────────────────

    async def cerrar(
        self, *, current_user: CurrentUser, data: CerrarLiquidacionRequest
    ) -> CerrarLiquidacionResponse:
        tid = current_user.tenant_id
        liq_repo = LiquidacionRepository(self._session, tid)

        cerradas = await liq_repo.cerrar_batch(data.cohorte_id, data.periodo)

        await self._audit().log(
            current_user=current_user,
            accion=LIQUIDACION_CERRAR,
            detalle={
                "cohorte_id": str(data.cohorte_id),
                "periodo": data.periodo,
                "cerradas": cerradas,
            },
            filas_afectadas=cerradas,
        )

        return CerrarLiquidacionResponse(
            cerradas=cerradas,
            cohorte_id=data.cohorte_id,
            periodo=data.periodo,
        )

    # ── List + Get ────────────────────────────────────────────────────────────

    async def list_liquidaciones(
        self,
        *,
        tenant_id: UUID,
        cohorte_id: UUID,
        periodo: str,
    ) -> list[LiquidacionResponse]:
        liq_repo = LiquidacionRepository(self._session, tenant_id)
        rows = await liq_repo.list_by_cohorte_periodo(cohorte_id, periodo)
        return [LiquidacionResponse.model_validate(r) for r in rows]

    async def get_liquidacion(
        self, *, id: UUID, tenant_id: UUID
    ) -> LiquidacionResponse:
        liq_repo = LiquidacionRepository(self._session, tenant_id)
        obj = await liq_repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return LiquidacionResponse.model_validate(obj)

    # ── KPIs ──────────────────────────────────────────────────────────────────

    async def get_kpis(
        self, *, tenant_id: UUID, cohorte_id: UUID, periodo: str
    ) -> KPIsLiquidacionResponse:
        liq_repo = LiquidacionRepository(self._session, tenant_id)
        rows = await liq_repo.list_by_cohorte_periodo(cohorte_id, periodo)

        total_sin_factura = sum(
            r.total for r in rows if not r.excluido_por_factura
        ) or Decimal("0")
        count_abierta = sum(1 for r in rows if r.estado == LiquidacionEstado.Abierta)
        count_cerrada = sum(1 for r in rows if r.estado == LiquidacionEstado.Cerrada)

        factura_repo = FacturaRepository(self._session, tenant_id)
        total_con_factura = await factura_repo.count_abonadas_por_periodo(periodo)

        return KPIsLiquidacionResponse(
            cohorte_id=cohorte_id,
            periodo=periodo,
            total_sin_factura=Decimal(total_sin_factura).quantize(_Q2),
            total_con_factura=total_con_factura,
            count_docentes=len(rows),
            count_abierta=count_abierta,
            count_cerrada=count_cerrada,
        )
