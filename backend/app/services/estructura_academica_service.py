"""EstructuraAcademicaService — business logic for Carrera, Cohorte, Materia.

All methods raise ValueError with a discriminated message:
  "not found"         → router maps to HTTP 404
  "ya existe"         → router maps to HTTP 409
  "carrera inactiva"  → router maps to HTTP 400
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import EstadoBasico
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.materia import Materia
from app.repositories.carrera_repository import CarreraRepository
from app.repositories.cohorte_repository import CohorteRepository
from app.repositories.materia_repository import MateriaRepository
from app.schemas.estructura_academica import (
    CarreraCreate,
    CarreraUpdate,
    CohorteCreate,
    CohorteUpdate,
    MateriaCreate,
    MateriaUpdate,
)


class EstructuraAcademicaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Carrera ────────────────────────────────────────────────────────────

    async def create_carrera(self, *, tenant_id: UUID, data: CarreraCreate) -> Carrera:
        repo = CarreraRepository(self._session, tenant_id)
        if await repo.get_by_codigo(data.codigo) is not None:
            raise ValueError(f"codigo ya existe: {data.codigo!r}")
        return await repo.create({"codigo": data.codigo, "nombre": data.nombre})

    async def list_carreras(self, *, tenant_id: UUID) -> list[Carrera]:
        repo = CarreraRepository(self._session, tenant_id)
        return list(await repo.list())

    async def get_carrera(self, *, id: UUID, tenant_id: UUID) -> Carrera:
        repo = CarreraRepository(self._session, tenant_id)
        carrera = await repo.get_active_by_id(id)
        if carrera is None:
            raise ValueError("not found")
        return carrera

    async def update_carrera(self, *, id: UUID, tenant_id: UUID, data: CarreraUpdate) -> Carrera:
        repo = CarreraRepository(self._session, tenant_id)
        carrera = await repo.get_active_by_id(id)
        if carrera is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if "codigo" in updates and updates["codigo"] != carrera.codigo:
            if await repo.get_by_codigo(updates["codigo"]) is not None:
                raise ValueError(f"codigo ya existe: {updates['codigo']!r}")
        updated = await repo.update(id, updates)
        if updated is None:
            raise ValueError("not found")
        return updated

    async def delete_carrera(self, *, id: UUID, tenant_id: UUID) -> None:
        repo = CarreraRepository(self._session, tenant_id)
        if await repo.get_active_by_id(id) is None:
            raise ValueError("not found")
        await repo.soft_delete(id)

    # ── Cohorte ────────────────────────────────────────────────────────────

    async def create_cohorte(self, *, tenant_id: UUID, data: CohorteCreate) -> Cohorte:
        carrera_repo = CarreraRepository(self._session, tenant_id)
        carrera = await carrera_repo.get_active_by_id(data.carrera_id)
        if carrera is None:
            raise ValueError("carrera not found")
        if carrera.estado != EstadoBasico.Activa:
            raise ValueError("carrera inactiva")
        cohorte_repo = CohorteRepository(self._session, tenant_id)
        if await cohorte_repo.get_by_nombre_carrera(data.nombre, data.carrera_id) is not None:
            raise ValueError(f"nombre ya existe: {data.nombre!r}")
        return await cohorte_repo.create(data.model_dump())

    async def list_cohortes(self, *, tenant_id: UUID, carrera_id: UUID | None = None) -> list[Cohorte]:
        repo = CohorteRepository(self._session, tenant_id)
        if carrera_id is not None:
            return await repo.list_by_carrera(carrera_id)
        return list(await repo.list())

    async def get_cohorte(self, *, id: UUID, tenant_id: UUID) -> Cohorte:
        repo = CohorteRepository(self._session, tenant_id)
        cohorte = await repo.get_active_by_id(id)
        if cohorte is None:
            raise ValueError("not found")
        return cohorte

    async def update_cohorte(self, *, id: UUID, tenant_id: UUID, data: CohorteUpdate) -> Cohorte:
        repo = CohorteRepository(self._session, tenant_id)
        cohorte = await repo.get_active_by_id(id)
        if cohorte is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if "nombre" in updates and updates["nombre"] != cohorte.nombre:
            if await repo.get_by_nombre_carrera(updates["nombre"], cohorte.carrera_id) is not None:
                raise ValueError(f"nombre ya existe: {updates['nombre']!r}")
        updated = await repo.update(id, updates)
        if updated is None:
            raise ValueError("not found")
        return updated

    async def delete_cohorte(self, *, id: UUID, tenant_id: UUID) -> None:
        repo = CohorteRepository(self._session, tenant_id)
        if await repo.get_active_by_id(id) is None:
            raise ValueError("not found")
        await repo.soft_delete(id)

    # ── Materia ────────────────────────────────────────────────────────────

    async def create_materia(self, *, tenant_id: UUID, data: MateriaCreate) -> Materia:
        repo = MateriaRepository(self._session, tenant_id)
        if await repo.get_by_codigo(data.codigo) is not None:
            raise ValueError(f"codigo ya existe: {data.codigo!r}")
        return await repo.create({"codigo": data.codigo, "nombre": data.nombre})

    async def list_materias(self, *, tenant_id: UUID) -> list[Materia]:
        repo = MateriaRepository(self._session, tenant_id)
        return list(await repo.list())

    async def get_materia(self, *, id: UUID, tenant_id: UUID) -> Materia:
        repo = MateriaRepository(self._session, tenant_id)
        materia = await repo.get_active_by_id(id)
        if materia is None:
            raise ValueError("not found")
        return materia

    async def update_materia(self, *, id: UUID, tenant_id: UUID, data: MateriaUpdate) -> Materia:
        repo = MateriaRepository(self._session, tenant_id)
        materia = await repo.get_active_by_id(id)
        if materia is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if "codigo" in updates and updates["codigo"] != materia.codigo:
            if await repo.get_by_codigo(updates["codigo"]) is not None:
                raise ValueError(f"codigo ya existe: {updates['codigo']!r}")
        updated = await repo.update(id, updates)
        if updated is None:
            raise ValueError("not found")
        return updated

    async def delete_materia(self, *, id: UUID, tenant_id: UUID) -> None:
        repo = MateriaRepository(self._session, tenant_id)
        if await repo.get_active_by_id(id) is None:
            raise ValueError("not found")
        await repo.soft_delete(id)
