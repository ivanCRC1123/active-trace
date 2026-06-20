"""AvisosService — business logic for C-15 avisos-y-acknowledgment.

Error convention (ValueError messages → HTTP codes in router):
  "not found"           → 404
  "materia not found"   → 404
  "cohorte not found"   → 404
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import AVISO_ACK, AVISO_CREAR
from app.models.aviso import Aviso, AcknowledgmentAviso
from app.repositories.asignacion_repository import AsignacionRepository
from app.repositories.aviso_repository import AckAvisoRepository, AvisoRepository
from app.repositories.cohorte_repository import CohorteRepository
from app.repositories.entrada_padron_repository import EntradaPadronRepository
from app.repositories.materia_repository import MateriaRepository
from app.schemas.auth import CurrentUser
from app.schemas.avisos import AvisoCreate, AvisoStats, AvisoUpdate
from app.services.audit_service import AuditService


class AvisosService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Internal FK validators ─────────────────────────────────────────

    async def _get_materia(self, materia_id: UUID, tenant_id: UUID):
        obj = await MateriaRepository(self._session, tenant_id).get_by_id(materia_id)
        if obj is None:
            raise ValueError("materia not found")
        return obj

    async def _get_cohorte(self, cohorte_id: UUID, tenant_id: UUID):
        obj = await CohorteRepository(self._session, tenant_id).get_by_id(cohorte_id)
        if obj is None:
            raise ValueError("cohorte not found")
        return obj

    # ── CRUD (avisos:publicar) ─────────────────────────────────────────

    async def create_aviso(
        self, *, tenant_id: UUID, data: AvisoCreate, current_user: CurrentUser
    ) -> Aviso:
        # scope_y_vigencia validated at schema level (AvisoCreate.model_validator)
        if data.materia_id is not None:
            await self._get_materia(data.materia_id, tenant_id)
        if data.cohorte_id is not None:
            await self._get_cohorte(data.cohorte_id, tenant_id)

        repo = AvisoRepository(self._session, tenant_id)
        aviso = await repo.create(data.model_dump())
        await AuditService(self._session).log(
            current_user=current_user,
            accion=AVISO_CREAR,
            detalle={"alcance": data.alcance, "titulo": data.titulo},
        )
        return aviso

    async def list_avisos(self, *, tenant_id: UUID) -> list[Aviso]:
        return await AvisoRepository(self._session, tenant_id).list_all()

    async def get_aviso(self, *, id: UUID, tenant_id: UUID) -> Aviso:
        obj = await AvisoRepository(self._session, tenant_id).get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return obj

    async def update_aviso(
        self, *, id: UUID, tenant_id: UUID, data: AvisoUpdate
    ) -> Aviso:
        repo = AvisoRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return obj
        updated = await repo.update(id, updates)
        return updated

    async def delete_aviso(self, *, id: UUID, tenant_id: UUID) -> bool:
        deleted = await AvisoRepository(self._session, tenant_id).soft_delete(id)
        if not deleted:
            raise ValueError("not found")
        return True

    async def stats_aviso(self, *, id: UUID, tenant_id: UUID) -> AvisoStats:
        repo = AvisoRepository(self._session, tenant_id)
        if await repo.get_by_id(id) is None:
            raise ValueError("not found")
        confirmaciones = await repo.count_confirmaciones(id)
        return AvisoStats(aviso_id=id, confirmaciones=confirmaciones)

    # ── Consumo (comunicacion:confirmar_aviso) ─────────────────────────

    async def mis_avisos(
        self, *, tenant_id: UUID, current_user: CurrentUser, now: datetime
    ) -> list[Aviso]:
        # Roles from JWT — PorRol scope (concern #2: closed catalog already enforced at creation)
        roles = set(current_user.roles)

        # Academic context from vigent asignaciones
        asigs = await AsignacionRepository(self._session, tenant_id).list_by_usuario(
            current_user.user_id,
            estado_vigencia="Vigente",
            today=date.today(),
        )
        materias: set[UUID] = {a.materia_id for a in asigs if a.materia_id}
        cohortes: set[UUID] = {a.cohorte_id for a in asigs if a.cohorte_id}

        # ALUMNO fallback: cohortes via active EntradaPadron
        padron_cohortes = await EntradaPadronRepository(
            self._session, tenant_id
        ).list_cohortes_activas_by_usuario(current_user.user_id)
        cohortes.update(padron_cohortes)

        # RN-18 + RN-20 + RN-19 all applied inside the repository query
        return await AvisoRepository(self._session, tenant_id).list_visibles_para_usuario(
            roles=roles,
            materias=materias,
            cohortes=cohortes,
            usuario_id=current_user.user_id,
            now=now,
        )

    async def confirmar_aviso(
        self, *, tenant_id: UUID, aviso_id: UUID, current_user: CurrentUser
    ) -> tuple[AcknowledgmentAviso, bool]:
        """Idempotent ack. Returns (ack, True) if newly created, (existing, False) otherwise."""
        av_repo = AvisoRepository(self._session, tenant_id)
        if await av_repo.get_by_id(aviso_id) is None:
            raise ValueError("not found")

        ack_repo = AckAvisoRepository(self._session, tenant_id)
        existing = await ack_repo.get_by_aviso_usuario(aviso_id, current_user.user_id)
        if existing is not None:
            return existing, False

        ack = await ack_repo.create_ack(aviso_id, current_user.user_id)
        await AuditService(self._session).log(
            current_user=current_user,
            accion=AVISO_ACK,
            detalle={"aviso_id": str(aviso_id), "idempotente": False},
        )
        return ack, True
