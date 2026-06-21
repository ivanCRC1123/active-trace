"""FacturaService — ABM + estado de Factura (E20, RN-39/40, C-18 Section 3).

Reglas:
  - Solo se puede crear una Factura para un usuario con facturador=True (RN-39).
  - estado: Pendiente | Abonada. Transición bidireccional.
  - Al pasar a Abonada: abonada_at = now(), audit FACTURA_ABONAR.
  - Al volver a Pendiente: abonada_at = None.
  - Soft-delete: nunca hard delete.
  - RBAC: facturas:gestionar (FINANZAS-only).
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import FACTURA_ABONAR
from app.models.base import FacturaEstado
from app.repositories.factura_repository import FacturaRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUser
from app.schemas.facturas import (
    FacturaCambiarEstadoRequest,
    FacturaCreate,
    FacturaResponse,
    FacturaUpdate,
)
from app.services.audit_service import AuditService


class FacturaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _audit(self) -> AuditService:
        return AuditService(self._session)

    async def crear(
        self, *, current_user: CurrentUser, data: FacturaCreate
    ) -> FacturaResponse:
        tid = current_user.tenant_id
        user_repo = UserRepository(self._session, tid)
        user = await user_repo.get_by_id(data.usuario_id)
        if user is None or not user.facturador:
            raise ValueError("usuario no es facturador — solo usuarios con facturador=true pueden presentar facturas")

        factura_repo = FacturaRepository(self._session, tid)
        factura = await factura_repo.create({
            "usuario_id": data.usuario_id,
            "periodo": data.periodo,
            "detalle": data.detalle,
            "referencia_archivo": data.referencia_archivo,
            "tamano_kb": data.tamano_kb,
        })
        return FacturaResponse.model_validate(factura)

    async def editar(
        self, *, current_user: CurrentUser, id: UUID, data: FacturaUpdate
    ) -> FacturaResponse:
        updates = data.model_dump(exclude_none=True)
        if not updates:
            raise ValueError("sin campos a actualizar")
        factura_repo = FacturaRepository(self._session, current_user.tenant_id)
        factura = await factura_repo.update(str(id), updates)
        if factura is None:
            raise ValueError("not found")
        return FacturaResponse.model_validate(factura)

    async def baja(self, *, current_user: CurrentUser, id: UUID) -> None:
        factura_repo = FacturaRepository(self._session, current_user.tenant_id)
        ok = await factura_repo.soft_delete(str(id))
        if not ok:
            raise ValueError("not found")

    async def cambiar_estado(
        self, *, current_user: CurrentUser, id: UUID, data: FacturaCambiarEstadoRequest
    ) -> FacturaResponse:
        factura_repo = FacturaRepository(self._session, current_user.tenant_id)
        factura = await factura_repo.get_by_id(str(id))
        if factura is None:
            raise ValueError("not found")

        updates: dict = {"estado": data.estado}
        if data.estado == FacturaEstado.Abonada:
            updates["abonada_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            updates["abonada_at"] = None

        factura = await factura_repo.update(str(id), updates)

        if data.estado == FacturaEstado.Abonada:
            await self._audit().log(
                current_user=current_user,
                accion=FACTURA_ABONAR,
                detalle={"factura_id": str(id), "periodo": factura.periodo},
                filas_afectadas=1,
            )

        return FacturaResponse.model_validate(factura)

    async def listar(
        self,
        *,
        tenant_id: UUID,
        usuario_id: UUID | None = None,
        estado: FacturaEstado | None = None,
        periodo: str | None = None,
        fecha_desde=None,
        fecha_hasta=None,
        q: str | None = None,
    ) -> list[FacturaResponse]:
        factura_repo = FacturaRepository(self._session, tenant_id)
        rows = await factura_repo.list_with_filters(
            usuario_id=usuario_id,
            estado=estado,
            periodo=periodo,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            q=q,
        )
        return [FacturaResponse.model_validate(r) for r in rows]

    async def get(self, *, id: UUID, tenant_id: UUID) -> FacturaResponse:
        factura_repo = FacturaRepository(self._session, tenant_id)
        factura = await factura_repo.get_by_id(str(id))
        if factura is None:
            raise ValueError("not found")
        return FacturaResponse.model_validate(factura)
