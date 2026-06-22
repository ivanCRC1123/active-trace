"""AsignacionService — business logic for Asignacion ABM with vigencia (C-07).

ValueError messages:
  "usuario not found"       → HTTP 404
  "rol not found"           → HTTP 404
  "asignacion not found"    → HTTP 404
  "rol ALUMNO"              → HTTP 400
  "hasta debe ser >= desde" → HTTP 400
"""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asignacion import Asignacion
from app.repositories.asignacion_repository import AsignacionRepository
from app.repositories.rol_repository import RolRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.asignaciones import (
    AsignacionCreate,
    AsignacionResponse,
    AsignacionUpdate,
    MeAsignacionItem,
)


class AsignacionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _repo(self, tenant_id: UUID) -> AsignacionRepository:
        return AsignacionRepository(self._session, tenant_id)

    @staticmethod
    def _vigencia(desde: date, hasta: date | None) -> str:
        today = date.today()
        if desde > today:
            return "Vencida"
        if hasta is not None and hasta < today:
            return "Vencida"
        return "Vigente"

    def _to_response(self, a: Asignacion) -> AsignacionResponse:
        return AsignacionResponse(
            id=a.id,
            tenant_id=a.tenant_id,
            usuario_id=a.usuario_id,
            rol_id=a.rol_id,
            materia_id=a.materia_id,
            carrera_id=a.carrera_id,
            cohorte_id=a.cohorte_id,
            responsable_id=a.responsable_id,
            comisiones=a.comisiones,
            desde=a.desde,
            hasta=a.hasta,
            estado_vigencia=self._vigencia(a.desde, a.hasta),
            created_at=a.created_at,
            updated_at=a.updated_at,
        )

    async def create_asignacion(
        self, *, tenant_id: UUID, data: AsignacionCreate
    ) -> AsignacionResponse:
        if await UsuarioRepository(self._session, tenant_id).get_by_id(data.usuario_id) is None:
            raise ValueError("usuario not found en este tenant")
        rol = await RolRepository(self._session, tenant_id).get_by_id(data.rol_id)
        if rol is None:
            raise ValueError("rol not found en este tenant")
        if rol.nombre == "ALUMNO":
            raise ValueError("no se puede asignar rol ALUMNO en una asignacion docente")
        if data.hasta is not None and data.hasta < data.desde:
            raise ValueError("hasta debe ser >= desde")
        a = await self._repo(tenant_id).create(data.model_dump())
        return self._to_response(a)

    async def list_asignaciones(
        self, *, tenant_id: UUID, vigente: bool | None = None
    ) -> list[AsignacionResponse]:
        today = date.today()
        repo = self._repo(tenant_id)
        if vigente is True:
            items = await repo.list_vigentes(today)
        elif vigente is False:
            items = await repo.list_vencidas(today)
        else:
            items = list(await repo.list())
        return [self._to_response(a) for a in items]

    async def get_asignacion(self, *, id: UUID, tenant_id: UUID) -> AsignacionResponse:
        a = await self._repo(tenant_id).get_by_id(id)
        if a is None:
            raise ValueError("asignacion not found")
        return self._to_response(a)

    async def update_asignacion(
        self, *, id: UUID, tenant_id: UUID, data: AsignacionUpdate
    ) -> AsignacionResponse:
        updated = await self._repo(tenant_id).update(id, data.model_dump(exclude_unset=True))
        if updated is None:
            raise ValueError("asignacion not found")
        return self._to_response(updated)

    async def delete_asignacion(self, *, id: UUID, tenant_id: UUID) -> None:
        if not await self._repo(tenant_id).soft_delete(id):
            raise ValueError("asignacion not found")

    async def list_mis_asignaciones(
        self, *, user_id: UUID, tenant_id: UUID
    ) -> list[MeAsignacionItem]:
        today = date.today()
        rows = await self._repo(tenant_id).list_by_usuario(
            user_id, estado_vigencia="Vigente", today=today
        )
        return [
            MeAsignacionItem(
                id=r.id,
                materia_id=r.materia_id,
                materia_nombre=r.materia_nombre,
                carrera_id=r.carrera_id,
                carrera_nombre=r.carrera_nombre,
                cohorte_id=r.cohorte_id,
                cohorte_nombre=r.cohorte_nombre,
                comisiones=r.comisiones,
                rol_nombre=r.rol_nombre,
                desde=r.desde,
                hasta=r.hasta,
            )
            for r in rows
        ]
