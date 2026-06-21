"""GuardiaService — C-13 guardias (F6.6).

Scoping "propio":
  - scope="own" (TUTOR, PROFESOR): solo guardias donde asignacion_id pertenece al usuario.
  - scope="all" (COORDINADOR, ADMIN): todo el tenant + acceso a export.

D-C13-6: campo fecha DATE incluido en Guardia.
Estado inicial: siempre "Pendiente", ignorando cualquier valor del body.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import GUARDIA_REGISTRAR
from app.models.asignacion import Asignacion
from app.models.carrera import Carrera
from app.models.cohorte import Cohorte
from app.models.guardia import Guardia
from app.models.materia import Materia
from app.models.user import User
from app.repositories.guardia_repository import GuardiaRepository
from app.schemas.auth import CurrentUser
from app.schemas.guardias import GuardiaCreate, GuardiaResponse, GuardiaUpdate
from app.services.audit_service import AuditService


def _to_response(g: Guardia) -> GuardiaResponse:
    return GuardiaResponse(
        id=g.id,
        asignacion_id=g.asignacion_id,
        materia_id=g.materia_id,
        carrera_id=g.carrera_id,
        cohorte_id=g.cohorte_id,
        dia=g.dia,
        fecha=g.fecha,
        horario=g.horario,
        estado=g.estado,
        comentarios=g.comentarios,
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


class GuardiaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _repo(self, tenant_id: UUID) -> GuardiaRepository:
        return GuardiaRepository(self._session, tenant_id)

    def _audit(self) -> AuditService:
        return AuditService(self._session)

    async def _get_asignacion_ids(self, usuario_id: UUID, tenant_id: UUID) -> list[UUID]:
        stmt = select(Asignacion.id).where(
            Asignacion.usuario_id == usuario_id,
            Asignacion.tenant_id == tenant_id,
            Asignacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _assert_asignacion_registrable(
        self, asignacion_id: UUID, current_user: CurrentUser, scope: str | None
    ) -> None:
        """Verifica que la asignacion exista en el tenant; si scope=own, que pertenezca al usuario."""
        stmt = select(Asignacion).where(
            Asignacion.id == asignacion_id,
            Asignacion.tenant_id == current_user.tenant_id,
            Asignacion.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        asig = result.scalar_one_or_none()
        if asig is None:
            raise ValueError("asignacion_no_existe")
        if scope == "own" and asig.usuario_id != current_user.user_id:
            raise PermissionError("asignacion_no_propia")

    async def _assert_propietario_o_admin(
        self, guardia: Guardia, current_user: CurrentUser, scope: str | None
    ) -> None:
        if scope == "all":
            return
        ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
        if guardia.asignacion_id not in ids:
            raise PermissionError("guardia_no_propia")

    # ── Registrar ────────────────────────────────────────────────────────────

    async def registrar(
        self, current_user: CurrentUser, data: GuardiaCreate, scope: str | None
    ) -> GuardiaResponse:
        await self._assert_asignacion_registrable(data.asignacion_id, current_user, scope)

        guardia = await self._repo(current_user.tenant_id).create({
            "asignacion_id": data.asignacion_id,
            "materia_id": data.materia_id,
            "carrera_id": data.carrera_id,
            "cohorte_id": data.cohorte_id,
            "dia": data.dia,
            "fecha": data.fecha,
            "horario": data.horario,
            "estado": "Pendiente",
            "comentarios": data.comentarios,
        })

        await self._audit().log(
            current_user=current_user,
            accion=GUARDIA_REGISTRAR,
            detalle={
                "guardia_id": str(guardia.id),
                "materia_id": str(data.materia_id),
                "asignacion_id": str(data.asignacion_id),
                "estado_inicial": "Pendiente",
            },
            materia_id=data.materia_id,
        )
        await self._session.commit()
        return _to_response(guardia)

    # ── Listar ────────────────────────────────────────────────────────────────

    async def listar(
        self,
        current_user: CurrentUser,
        scope: str | None,
        materia_id: UUID | None = None,
        carrera_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
        asignacion_id: UUID | None = None,
    ) -> list[GuardiaResponse]:
        repo = self._repo(current_user.tenant_id)
        if scope == "own":
            ids = await self._get_asignacion_ids(current_user.user_id, current_user.tenant_id)
            guardias = await repo.list_by_asignaciones(
                ids, materia_id, carrera_id, cohorte_id, estado, fecha_desde, fecha_hasta
            )
        else:
            guardias = await repo.list_all(
                materia_id, carrera_id, cohorte_id, estado, fecha_desde, fecha_hasta, asignacion_id
            )
        return [_to_response(g) for g in guardias]

    # ── Editar ────────────────────────────────────────────────────────────────

    async def editar(
        self,
        current_user: CurrentUser,
        guardia_id: UUID,
        data: GuardiaUpdate,
        scope: str | None,
    ) -> GuardiaResponse:
        guardia = await self._repo(current_user.tenant_id).get_by_id(guardia_id)
        if guardia is None:
            raise LookupError("guardia_no_encontrada")
        await self._assert_propietario_o_admin(guardia, current_user, scope)

        cambios = {k: v for k, v in data.model_dump().items() if v is not None}
        if not cambios:
            return _to_response(guardia)

        guardia = await self._repo(current_user.tenant_id).update(guardia_id, cambios)
        await self._session.commit()
        return _to_response(guardia)  # type: ignore[arg-type]

    # ── Export CSV ───────────────────────────────────────────────────────────

    async def exportar_csv(
        self,
        current_user: CurrentUser,
        scope: str | None,
        materia_id: UUID | None = None,
        carrera_id: UUID | None = None,
        cohorte_id: UUID | None = None,
        estado: str | None = None,
        fecha_desde: date | None = None,
        fecha_hasta: date | None = None,
    ) -> str:
        if scope != "all":
            raise PermissionError("export_requiere_scope_all")

        stmt = (
            select(
                Guardia,
                User.nombre.label("doc_nombre"),
                User.apellidos.label("doc_apellidos"),
                Materia.nombre.label("mat_nombre"),
                Carrera.nombre.label("car_nombre"),
                Cohorte.nombre.label("coh_nombre"),
            )
            .join(Asignacion, Asignacion.id == Guardia.asignacion_id)
            .join(User, User.id == Asignacion.usuario_id)
            .outerjoin(Materia, Materia.id == Guardia.materia_id)
            .outerjoin(Carrera, Carrera.id == Guardia.carrera_id)
            .outerjoin(Cohorte, Cohorte.id == Guardia.cohorte_id)
            .where(
                Guardia.tenant_id == current_user.tenant_id,
                Guardia.deleted_at.is_(None),
            )
        )
        if materia_id:
            stmt = stmt.where(Guardia.materia_id == materia_id)
        if carrera_id:
            stmt = stmt.where(Guardia.carrera_id == carrera_id)
        if cohorte_id:
            stmt = stmt.where(Guardia.cohorte_id == cohorte_id)
        if estado:
            stmt = stmt.where(Guardia.estado == estado)
        if fecha_desde:
            stmt = stmt.where(Guardia.fecha >= fecha_desde)
        if fecha_hasta:
            stmt = stmt.where(Guardia.fecha <= fecha_hasta)
        stmt = stmt.order_by(Guardia.fecha.asc().nullsfirst(), Guardia.created_at.asc())

        result = await self._session.execute(stmt)
        rows = result.all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "asignacion_id", "docente_nombre", "docente_apellidos",
            "materia", "carrera", "cohorte",
            "dia", "fecha", "horario", "estado", "comentarios", "creada_at",
        ])
        for row in rows:
            g: Guardia = row[0]
            writer.writerow([
                str(g.asignacion_id),
                row.doc_nombre,
                row.doc_apellidos,
                row.mat_nombre or "",
                row.car_nombre or "",
                row.coh_nombre or "",
                g.dia,
                str(g.fecha) if g.fecha else "",
                g.horario,
                g.estado,
                g.comentarios or "",
                g.created_at.isoformat(),
            ])
        return output.getvalue()
