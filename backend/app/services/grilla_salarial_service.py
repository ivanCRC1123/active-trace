"""GrillaSalarialService — business logic for MateriaGrupo (E16a), SalarioBase (E17), SalarioPlus (E18).

Error convention (ValueError messages → HTTP codes in router):
  "not found"           → 404
  "materia not found"   → 404
  "ya existe"           → 409
"""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import GRILLA_SALARIAL_OPERAR
from app.models.base import RolLiquidable
from app.models.materia_grupo import MateriaGrupo
from app.models.salario_base import SalarioBase
from app.models.salario_plus import SalarioPlus
from app.repositories.materia_grupo_repository import MateriaGrupoRepository
from app.repositories.materia_repository import MateriaRepository
from app.repositories.salario_base_repository import SalarioBaseRepository
from app.repositories.salario_plus_repository import SalarioPlusRepository
from app.schemas.auth import CurrentUser
from app.schemas.grilla_salarial import (
    MateriaGrupoCreate,
    SalarioBaseCreate,
    SalarioBaseUpdate,
    SalarioPlusCreate,
    SalarioPlusUpdate,
)
from app.services.audit_service import AuditService


class GrillaSalarialService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _audit(self) -> AuditService:
        return AuditService(self._session)

    # ── Internal FK validators ─────────────────────────────────────────────

    async def _get_materia(self, materia_id: UUID, tenant_id: UUID):
        repo = MateriaRepository(self._session, tenant_id)
        obj = await repo.get_by_id(materia_id)
        if obj is None:
            raise ValueError("materia not found")
        return obj

    # ── MateriaGrupo ───────────────────────────────────────────────────────

    async def create_materia_grupo(
        self, *, current_user: CurrentUser, data: MateriaGrupoCreate
    ) -> MateriaGrupo:
        tenant_id = current_user.tenant_id
        await self._get_materia(data.materia_id, tenant_id)
        repo = MateriaGrupoRepository(self._session, tenant_id)
        if await repo.get_by_materia_y_grupo(data.materia_id, data.grupo):
            raise ValueError("materia_grupo ya existe")
        obj = await repo.create(
            {"materia_id": data.materia_id, "grupo": data.grupo}
        )
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={"op": "create_materia_grupo", "id": str(obj.id)},
        )
        return obj

    async def list_materia_grupos(
        self,
        *,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        grupo: str | None = None,
    ) -> list[MateriaGrupo]:
        repo = MateriaGrupoRepository(self._session, tenant_id)
        if materia_id is not None:
            return await repo.list_by_materia(materia_id)
        if grupo is not None:
            return await repo.list_by_grupo(grupo)
        return list(await repo.list())

    async def get_materia_grupo(self, *, id: UUID, tenant_id: UUID) -> MateriaGrupo:
        repo = MateriaGrupoRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return obj

    async def delete_materia_grupo(
        self, *, id: UUID, current_user: CurrentUser
    ) -> None:
        repo = MateriaGrupoRepository(self._session, current_user.tenant_id)
        deleted = await repo.soft_delete(id)
        if not deleted:
            raise ValueError("not found")
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={"op": "delete_materia_grupo", "id": str(id)},
        )

    # ── SalarioBase ────────────────────────────────────────────────────────

    async def create_salario_base(
        self, *, current_user: CurrentUser, data: SalarioBaseCreate
    ) -> SalarioBase:
        tenant_id = current_user.tenant_id
        repo = SalarioBaseRepository(self._session, tenant_id)
        obj = await repo.create(
            {
                "rol": data.rol,
                "monto": data.monto,
                "desde": data.desde,
                "hasta": data.hasta,
            }
        )
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={"op": "create_salario_base", "id": str(obj.id), "rol": data.rol.value},
        )
        return obj

    async def list_salario_base(
        self, *, tenant_id: UUID, rol: RolLiquidable | None = None
    ) -> list[SalarioBase]:
        repo = SalarioBaseRepository(self._session, tenant_id)
        if rol is not None:
            return await repo.list_by_rol(rol)
        return list(await repo.list())

    async def get_salario_base(self, *, id: UUID, tenant_id: UUID) -> SalarioBase:
        repo = SalarioBaseRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return obj

    async def get_salario_base_vigente(
        self, *, tenant_id: UUID, rol: RolLiquidable, fecha: date
    ) -> SalarioBase | None:
        repo = SalarioBaseRepository(self._session, tenant_id)
        return await repo.get_vigente(rol, fecha)

    async def update_salario_base(
        self, *, id: UUID, current_user: CurrentUser, data: SalarioBaseUpdate
    ) -> SalarioBase:
        repo = SalarioBaseRepository(self._session, current_user.tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return obj
        updated = await repo.update(id, updates)
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={"op": "update_salario_base", "id": str(id), "fields": list(updates)},
        )
        return updated

    async def delete_salario_base(
        self, *, id: UUID, current_user: CurrentUser
    ) -> None:
        repo = SalarioBaseRepository(self._session, current_user.tenant_id)
        deleted = await repo.soft_delete(id)
        if not deleted:
            raise ValueError("not found")
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={"op": "delete_salario_base", "id": str(id)},
        )

    # ── SalarioPlus ────────────────────────────────────────────────────────

    async def create_salario_plus(
        self, *, current_user: CurrentUser, data: SalarioPlusCreate
    ) -> SalarioPlus:
        tenant_id = current_user.tenant_id
        repo = SalarioPlusRepository(self._session, tenant_id)
        obj = await repo.create(
            {
                "grupo": data.grupo,
                "rol": data.rol,
                "descripcion": data.descripcion,
                "monto": data.monto,
                "desde": data.desde,
                "hasta": data.hasta,
            }
        )
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={
                "op": "create_salario_plus",
                "id": str(obj.id),
                "grupo": data.grupo,
                "rol": data.rol.value,
            },
        )
        return obj

    async def list_salario_plus(
        self,
        *,
        tenant_id: UUID,
        grupo: str | None = None,
        rol: RolLiquidable | None = None,
    ) -> list[SalarioPlus]:
        repo = SalarioPlusRepository(self._session, tenant_id)
        if grupo is not None:
            return await repo.list_by_grupo(grupo)
        if rol is not None:
            return await repo.list_by_rol(rol)
        return list(await repo.list())

    async def get_salario_plus(self, *, id: UUID, tenant_id: UUID) -> SalarioPlus:
        repo = SalarioPlusRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return obj

    async def get_salario_plus_vigente(
        self, *, tenant_id: UUID, grupo: str, rol: RolLiquidable, fecha: date
    ) -> SalarioPlus | None:
        repo = SalarioPlusRepository(self._session, tenant_id)
        return await repo.get_vigente(grupo, rol, fecha)

    async def update_salario_plus(
        self, *, id: UUID, current_user: CurrentUser, data: SalarioPlusUpdate
    ) -> SalarioPlus:
        repo = SalarioPlusRepository(self._session, current_user.tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return obj
        updated = await repo.update(id, updates)
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={"op": "update_salario_plus", "id": str(id), "fields": list(updates)},
        )
        return updated

    async def delete_salario_plus(
        self, *, id: UUID, current_user: CurrentUser
    ) -> None:
        repo = SalarioPlusRepository(self._session, current_user.tenant_id)
        deleted = await repo.soft_delete(id)
        if not deleted:
            raise ValueError("not found")
        await self._audit().log(
            current_user=current_user,
            accion=GRILLA_SALARIAL_OPERAR,
            detalle={"op": "delete_salario_plus", "id": str(id)},
        )
