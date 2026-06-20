"""Repositories for C-14 evaluation models (E14)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluacion import (
    ConvocadoEvaluacion,
    EstadoReserva,
    Evaluacion,
    ResultadoEvaluacion,
    ReservaEvaluacion,
)
from app.models.base import TipoEvaluacion
from app.repositories.base import BaseRepository


class EvaluacionRepository(BaseRepository[Evaluacion]):
    @property
    def model_class(self) -> type[Evaluacion]:
        return Evaluacion

    async def get_by_instancia(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        tipo: TipoEvaluacion,
        instancia: str,
    ) -> Evaluacion | None:
        stmt = select(Evaluacion).where(
            Evaluacion.tenant_id == self._tenant_id,
            Evaluacion.materia_id == materia_id,
            Evaluacion.cohorte_id == cohorte_id,
            Evaluacion.tipo == tipo,
            Evaluacion.instancia == instancia,
            Evaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_materia_cohorte(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
    ) -> list[Evaluacion]:
        stmt = select(Evaluacion).where(
            Evaluacion.tenant_id == self._tenant_id,
            Evaluacion.materia_id == materia_id,
            Evaluacion.cohorte_id == cohorte_id,
            Evaluacion.deleted_at.is_(None),
        ).order_by(Evaluacion.created_at.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_reservas_activas(self, evaluacion_id: UUID) -> int:
        stmt = select(func.count()).where(
            ReservaEvaluacion.tenant_id == self._tenant_id,
            ReservaEvaluacion.evaluacion_id == evaluacion_id,
            ReservaEvaluacion.estado == EstadoReserva.Activa,
            ReservaEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_convocados(self, evaluacion_id: UUID) -> int:
        stmt = select(func.count()).where(
            ConvocadoEvaluacion.tenant_id == self._tenant_id,
            ConvocadoEvaluacion.evaluacion_id == evaluacion_id,
            ConvocadoEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_resultados(self, evaluacion_id: UUID) -> int:
        stmt = select(func.count()).where(
            ResultadoEvaluacion.tenant_id == self._tenant_id,
            ResultadoEvaluacion.evaluacion_id == evaluacion_id,
            ResultadoEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_all_convocados(self) -> int:
        stmt = select(func.count()).where(
            ConvocadoEvaluacion.tenant_id == self._tenant_id,
            ConvocadoEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_all_instancias(self) -> int:
        stmt = select(func.count()).where(
            Evaluacion.tenant_id == self._tenant_id,
            Evaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_all_reservas_activas(self) -> int:
        stmt = select(func.count()).where(
            ReservaEvaluacion.tenant_id == self._tenant_id,
            ReservaEvaluacion.estado == EstadoReserva.Activa,
            ReservaEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def count_all_resultados(self) -> int:
        stmt = select(func.count()).where(
            ResultadoEvaluacion.tenant_id == self._tenant_id,
            ResultadoEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0


class ConvocadoRepository(BaseRepository[ConvocadoEvaluacion]):
    @property
    def model_class(self) -> type[ConvocadoEvaluacion]:
        return ConvocadoEvaluacion

    async def list_by_evaluacion(self, evaluacion_id: UUID) -> list[ConvocadoEvaluacion]:
        stmt = select(ConvocadoEvaluacion).where(
            ConvocadoEvaluacion.tenant_id == self._tenant_id,
            ConvocadoEvaluacion.evaluacion_id == evaluacion_id,
            ConvocadoEvaluacion.deleted_at.is_(None),
        ).order_by(ConvocadoEvaluacion.apellidos.asc(), ConvocadoEvaluacion.nombre.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_email_hash(
        self, evaluacion_id: UUID, email_hash: str
    ) -> ConvocadoEvaluacion | None:
        stmt = select(ConvocadoEvaluacion).where(
            ConvocadoEvaluacion.tenant_id == self._tenant_id,
            ConvocadoEvaluacion.evaluacion_id == evaluacion_id,
            ConvocadoEvaluacion.email_hash == email_hash,
            ConvocadoEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_usuario(
        self, evaluacion_id: UUID, usuario_id: UUID
    ) -> ConvocadoEvaluacion | None:
        stmt = select(ConvocadoEvaluacion).where(
            ConvocadoEvaluacion.tenant_id == self._tenant_id,
            ConvocadoEvaluacion.evaluacion_id == evaluacion_id,
            ConvocadoEvaluacion.usuario_id == usuario_id,
            ConvocadoEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_create(
        self,
        tenant_id: UUID,
        evaluacion_id: UUID,
        filas: list[dict],
    ) -> int:
        """Insert a batch of convocados idempotently; return count of inserted rows."""
        from app.core.encryption import hmac_email  # noqa: PLC0415

        inserted = 0
        for fila in filas:
            email_hash = hmac_email(fila["email"])
            usuario_id = fila.get("usuario_id")

            if usuario_id is not None:
                existing = await self.get_by_usuario(evaluacion_id, usuario_id)
            else:
                existing = await self.get_by_email_hash(evaluacion_id, email_hash)

            if existing is not None:
                continue

            convocado = ConvocadoEvaluacion(
                tenant_id=tenant_id,
                evaluacion_id=evaluacion_id,
                usuario_id=usuario_id,
                nombre=fila["nombre"],
                apellidos=fila["apellidos"],
                email_cifrado=fila["email"],
                email_hash=email_hash,
            )
            self._session.add(convocado)
            await self._session.flush()
            inserted += 1

        return inserted


class ReservaRepository(BaseRepository[ReservaEvaluacion]):
    @property
    def model_class(self) -> type[ReservaEvaluacion]:
        return ReservaEvaluacion

    async def get_activa_by_alumno(
        self, evaluacion_id: UUID, alumno_id: UUID
    ) -> ReservaEvaluacion | None:
        stmt = select(ReservaEvaluacion).where(
            ReservaEvaluacion.tenant_id == self._tenant_id,
            ReservaEvaluacion.evaluacion_id == evaluacion_id,
            ReservaEvaluacion.alumno_id == alumno_id,
            ReservaEvaluacion.estado == EstadoReserva.Activa,
            ReservaEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_any_by_alumno(
        self, evaluacion_id: UUID, alumno_id: UUID
    ) -> ReservaEvaluacion | None:
        """Returns any (including Cancelada) non-deleted reservation for alumno."""
        stmt = select(ReservaEvaluacion).where(
            ReservaEvaluacion.tenant_id == self._tenant_id,
            ReservaEvaluacion.evaluacion_id == evaluacion_id,
            ReservaEvaluacion.alumno_id == alumno_id,
            ReservaEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_activas_by_evaluacion(
        self, evaluacion_id: UUID
    ) -> list[ReservaEvaluacion]:
        stmt = select(ReservaEvaluacion).where(
            ReservaEvaluacion.tenant_id == self._tenant_id,
            ReservaEvaluacion.evaluacion_id == evaluacion_id,
            ReservaEvaluacion.estado == EstadoReserva.Activa,
            ReservaEvaluacion.deleted_at.is_(None),
        ).order_by(ReservaEvaluacion.fecha_hora.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_activas(self, evaluacion_id: UUID) -> int:
        stmt = select(func.count()).where(
            ReservaEvaluacion.tenant_id == self._tenant_id,
            ReservaEvaluacion.evaluacion_id == evaluacion_id,
            ReservaEvaluacion.estado == EstadoReserva.Activa,
            ReservaEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0


class ResultadoRepository(BaseRepository[ResultadoEvaluacion]):
    @property
    def model_class(self) -> type[ResultadoEvaluacion]:
        return ResultadoEvaluacion

    async def get_by_alumno(
        self, evaluacion_id: UUID, alumno_id: UUID
    ) -> ResultadoEvaluacion | None:
        stmt = select(ResultadoEvaluacion).where(
            ResultadoEvaluacion.tenant_id == self._tenant_id,
            ResultadoEvaluacion.evaluacion_id == evaluacion_id,
            ResultadoEvaluacion.alumno_id == alumno_id,
            ResultadoEvaluacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_evaluacion(self, evaluacion_id: UUID) -> list[ResultadoEvaluacion]:
        stmt = select(ResultadoEvaluacion).where(
            ResultadoEvaluacion.tenant_id == self._tenant_id,
            ResultadoEvaluacion.evaluacion_id == evaluacion_id,
            ResultadoEvaluacion.deleted_at.is_(None),
        ).order_by(ResultadoEvaluacion.alumno_id.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
