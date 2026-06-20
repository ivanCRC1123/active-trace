"""ProgramasService — business logic for ProgramaMateria (E16) and FechaAcademica (E15).

Error convention (ValueError messages → HTTP codes in router):
  "not found"           → 404
  "materia not found"   → 404
  "carrera not found"   → 404
  "cohorte not found"   → 404
  "programa ya existe"  → 409
  "fecha ya existe"     → 409
"""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import TipoEvaluacion
from app.models.fecha_academica import FechaAcademica
from app.models.programa_materia import ProgramaMateria
from app.repositories.carrera_repository import CarreraRepository
from app.repositories.cohorte_repository import CohorteRepository
from app.repositories.fecha_academica_repository import FechaAcademicaRepository
from app.repositories.materia_repository import MateriaRepository
from app.repositories.programa_materia_repository import ProgramaMateriaRepository
from app.schemas.programas_y_fechas import (
    FechaAcademicaCreate,
    FechaAcademicaUpdate,
    ProgramaMateriaCreate,
    ProgramaMateriaUpdate,
)

_TIPO_LABEL = {
    TipoEvaluacion.Parcial: "Parciales",
    TipoEvaluacion.TP: "Trabajos Prácticos",
    TipoEvaluacion.Coloquio: "Coloquios",
    TipoEvaluacion.Recuperatorio: "Recuperatorios",
}

_NUMERO_LABEL = {
    1: "1er", 2: "2do", 3: "3er", 4: "4to",
    5: "5to", 6: "6to", 7: "7mo", 8: "8vo",
}

_MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _formato_fecha(d: date) -> str:
    return f"{d.day} de {_MESES_ES[d.month]} de {d.year}"


def _numero_ordinal(n: int) -> str:
    return _NUMERO_LABEL.get(n, f"{n}°")


class ProgramasService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Internal FK validators ─────────────────────────────────────────────

    async def _get_materia(self, materia_id: UUID, tenant_id: UUID):
        repo = MateriaRepository(self._session, tenant_id)
        obj = await repo.get_by_id(materia_id)
        if obj is None:
            raise ValueError("materia not found")
        return obj

    async def _get_carrera(self, carrera_id: UUID, tenant_id: UUID):
        repo = CarreraRepository(self._session, tenant_id)
        obj = await repo.get_active_by_id(carrera_id)
        if obj is None:
            raise ValueError("carrera not found")
        return obj

    async def _get_cohorte(self, cohorte_id: UUID, tenant_id: UUID):
        repo = CohorteRepository(self._session, tenant_id)
        obj = await repo.get_by_id(cohorte_id)
        if obj is None:
            raise ValueError("cohorte not found")
        return obj

    # ── ProgramaMateria ────────────────────────────────────────────────────

    async def create_programa(
        self, *, tenant_id: UUID, data: ProgramaMateriaCreate
    ) -> ProgramaMateria:
        await self._get_materia(data.materia_id, tenant_id)
        await self._get_carrera(data.carrera_id, tenant_id)
        await self._get_cohorte(data.cohorte_id, tenant_id)
        repo = ProgramaMateriaRepository(self._session, tenant_id)
        if await repo.get_by_combinacion(data.materia_id, data.carrera_id, data.cohorte_id):
            raise ValueError("programa ya existe")
        return await repo.create(
            {
                "materia_id": data.materia_id,
                "carrera_id": data.carrera_id,
                "cohorte_id": data.cohorte_id,
                "titulo": data.titulo,
                "referencia_archivo": data.referencia_archivo,
            }
        )

    async def list_programas(
        self,
        *,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        carrera_id: UUID | None = None,
        cohorte_id: UUID | None = None,
    ) -> list[ProgramaMateria]:
        repo = ProgramaMateriaRepository(self._session, tenant_id)
        if materia_id is not None:
            return await repo.list_by_materia(materia_id)
        if cohorte_id is not None:
            return await repo.list_by_cohorte(cohorte_id)
        return list(await repo.list())

    async def get_programa(self, *, id: UUID, tenant_id: UUID) -> ProgramaMateria:
        repo = ProgramaMateriaRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return obj

    async def update_programa(
        self, *, id: UUID, tenant_id: UUID, data: ProgramaMateriaUpdate
    ) -> ProgramaMateria:
        repo = ProgramaMateriaRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return obj
        return await repo.update(id, updates)

    async def delete_programa(self, *, id: UUID, tenant_id: UUID) -> bool:
        repo = ProgramaMateriaRepository(self._session, tenant_id)
        deleted = await repo.soft_delete(id)
        if not deleted:
            raise ValueError("not found")
        return True

    # ── FechaAcademica ─────────────────────────────────────────────────────

    async def create_fecha(
        self, *, tenant_id: UUID, data: FechaAcademicaCreate
    ) -> FechaAcademica:
        await self._get_materia(data.materia_id, tenant_id)
        await self._get_cohorte(data.cohorte_id, tenant_id)
        repo = FechaAcademicaRepository(self._session, tenant_id)
        if await repo.get_by_instancia(
            data.materia_id, data.cohorte_id, data.tipo, data.numero, data.periodo
        ):
            raise ValueError("fecha ya existe")
        return await repo.create(
            {
                "materia_id": data.materia_id,
                "cohorte_id": data.cohorte_id,
                "tipo": data.tipo,
                "numero": data.numero,
                "periodo": data.periodo,
                "fecha": data.fecha,
                "titulo": data.titulo,
            }
        )

    async def list_fechas(
        self,
        *,
        tenant_id: UUID,
        materia_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        periodo: str | None = None,
    ) -> list[FechaAcademica]:
        repo = FechaAcademicaRepository(self._session, tenant_id)
        if materia_id is not None and cohorte_id is not None:
            return await repo.list_by_materia_cohorte(materia_id, cohorte_id, periodo)
        if cohorte_id is not None:
            return await repo.list_by_cohorte(cohorte_id, periodo)
        return list(await repo.list())

    async def get_fecha(self, *, id: UUID, tenant_id: UUID) -> FechaAcademica:
        repo = FechaAcademicaRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        return obj

    async def update_fecha(
        self, *, id: UUID, tenant_id: UUID, data: FechaAcademicaUpdate
    ) -> FechaAcademica:
        repo = FechaAcademicaRepository(self._session, tenant_id)
        obj = await repo.get_by_id(id)
        if obj is None:
            raise ValueError("not found")
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return obj
        return await repo.update(id, updates)

    async def delete_fecha(self, *, id: UUID, tenant_id: UUID) -> bool:
        repo = FechaAcademicaRepository(self._session, tenant_id)
        deleted = await repo.soft_delete(id)
        if not deleted:
            raise ValueError("not found")
        return True

    async def generar_fragmento_lms(
        self,
        *,
        tenant_id: UUID,
        materia_id: UUID,
        cohorte_id: UUID,
        periodo: str | None = None,
    ) -> str:
        materia = await self._get_materia(materia_id, tenant_id)
        cohorte = await self._get_cohorte(cohorte_id, tenant_id)
        repo = FechaAcademicaRepository(self._session, tenant_id)
        fechas = await repo.list_by_materia_cohorte(materia_id, cohorte_id, periodo)
        if not fechas:
            return ""

        header = f"## Fechas académicas — {materia.nombre} | Cohorte {cohorte.nombre}"
        lines = [header, ""]

        grupos: dict[TipoEvaluacion, list[FechaAcademica]] = {}
        for f in fechas:
            grupos.setdefault(f.tipo, []).append(f)

        for tipo in [TipoEvaluacion.Parcial, TipoEvaluacion.TP, TipoEvaluacion.Coloquio, TipoEvaluacion.Recuperatorio]:
            if tipo not in grupos:
                continue
            lines.append(f"### {_TIPO_LABEL[tipo]}")
            for f in grupos[tipo]:
                label = f"**{_numero_ordinal(f.numero)} {tipo.value}**"
                lines.append(f"- {label} — {_formato_fecha(f.fecha)}")
            lines.append("")

        return "\n".join(lines).rstrip()
