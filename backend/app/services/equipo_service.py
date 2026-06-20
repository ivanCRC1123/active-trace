"""EquipoService — semantic team operations (C-08).

Covers F4.2–F4.7: mis-equipos, list-equipo, masiva, clonar, vigencia-bloque, exportar.
All DB access is via AsignacionRepository (and FK-validation repos). No SQL in this service.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import ASIGNACION_MODIFICAR
from app.models.asignacion import Asignacion
from app.repositories.asignacion_repository import AsignacionConNombres, AsignacionRepository
from app.repositories.carrera_repository import CarreraRepository
from app.repositories.cohorte_repository import CohorteRepository
from app.repositories.materia_repository import MateriaRepository
from app.repositories.rol_repository import RolRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import CurrentUser
from app.schemas.equipos import (
    AsignacionEquipoResponse,
    AsignacionMasivaRequest,
    ClonarEquipoRequest,
    ClonarOmitido,
    ClonarResult,
    EquipoFiltros,
    MasivaResult,
    MisEquiposFiltros,
    VigenciaBloqueRequest,
    VigenciaBloqueResult,
)
from app.services.audit_service import AuditService


class EquipoService:
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

    @staticmethod
    def _to_response(acn: AsignacionConNombres) -> AsignacionEquipoResponse:
        return AsignacionEquipoResponse(
            id=acn.id,
            usuario_id=acn.usuario_id,
            usuario_nombre=acn.usuario_nombre,
            usuario_apellidos=acn.usuario_apellidos,
            rol_id=acn.rol_id,
            rol=acn.rol_nombre,
            materia_id=acn.materia_id,
            materia_nombre=acn.materia_nombre,
            carrera_id=acn.carrera_id,
            carrera_nombre=acn.carrera_nombre,
            cohorte_id=acn.cohorte_id,
            cohorte_nombre=acn.cohorte_nombre,
            comisiones=acn.comisiones,
            responsable_id=acn.responsable_id,
            desde=acn.desde,
            hasta=acn.hasta,
            estado_vigencia=EquipoService._vigencia(acn.desde, acn.hasta),
        )

    # ── F4.2 mis-equipos ─────────────────────────────────────────────

    async def mis_equipos(
        self, *, tenant_id: UUID, usuario_id: UUID, filtros: MisEquiposFiltros
    ) -> list[AsignacionEquipoResponse]:
        rows = await self._repo(tenant_id).list_by_usuario(
            usuario_id,
            materia_id=filtros.materia_id,
            carrera_id=filtros.carrera_id,
            cohorte_id=filtros.cohorte_id,
            rol=filtros.rol,
            estado_vigencia=filtros.estado_vigencia,
            today=date.today(),
        )
        return [self._to_response(r) for r in rows]

    # ── F4.3 list equipo ─────────────────────────────────────────────

    async def list_equipo(
        self, *, tenant_id: UUID, filtros: EquipoFiltros
    ) -> list[AsignacionEquipoResponse]:
        rows = await self._repo(tenant_id).list_equipo(
            materia_id=filtros.materia_id,
            carrera_id=filtros.carrera_id,
            cohorte_id=filtros.cohorte_id,
            usuario_id=filtros.usuario_id,
            responsable_id=filtros.responsable_id,
            rol=filtros.rol,
            estado_vigencia=filtros.estado_vigencia,
            today=date.today(),
            limit=filtros.limit,
            offset=filtros.offset,
        )
        return [self._to_response(r) for r in rows]

    # ── F4.4 masiva ───────────────────────────────────────────────────

    async def asignar_masiva(
        self,
        *,
        tenant_id: UUID,
        payload: AsignacionMasivaRequest,
        current_user: CurrentUser,
        ip: str | None = None,
    ) -> MasivaResult:
        # -- Pasada 1: validar todos los user_ids y contexto --
        u_repo = UsuarioRepository(self._session, tenant_id)
        r_repo = RolRepository(self._session, tenant_id)

        invalidos: list[str] = []
        for uid in payload.usuario_ids:
            if await u_repo.get_by_id(uid) is None:
                invalidos.append(str(uid))

        if invalidos:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"mensaje": "usuario_ids inválidos", "usuario_ids_invalidos": invalidos},
            )

        rol = await r_repo.get_by_id(payload.rol_id)
        if rol is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rol not found")
        if rol.nombre == "ALUMNO":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="no se puede asignar rol ALUMNO en una asignacion docente",
            )

        await self._validar_contexto_fks(tenant_id, payload.materia_id, payload.carrera_id, payload.cohorte_id)

        # Verificar duplicados vigentes
        hoy = date.today()
        repo = self._repo(tenant_id)
        duplicados: list[str] = []
        for uid in payload.usuario_ids:
            ya = await repo.existe_vigente_en_destino(
                usuario_id=uid,
                rol_id=payload.rol_id,
                materia_id=payload.materia_id,
                carrera_id=payload.carrera_id,
                cohorte_id=payload.cohorte_id,
                today=hoy,
            )
            if ya:
                duplicados.append(str(uid))

        if duplicados:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"mensaje": "asignación vigente ya existe", "usuario_ids_duplicados": duplicados},
            )

        # -- Pasada 2: insertar en una sola transacción --
        nuevas: list[Asignacion] = []
        for uid in payload.usuario_ids:
            a = Asignacion(
                tenant_id=tenant_id,
                usuario_id=uid,
                rol_id=payload.rol_id,
                materia_id=payload.materia_id,
                carrera_id=payload.carrera_id,
                cohorte_id=payload.cohorte_id,
                comisiones=payload.comisiones,
                responsable_id=payload.responsable_id,
                desde=payload.desde,
                hasta=payload.hasta,
            )
            self._session.add(a)
            nuevas.append(a)

        await self._session.flush()
        for a in nuevas:
            await self._session.refresh(a)

        await AuditService(self._session).log(
            current_user=current_user,
            accion=ASIGNACION_MODIFICAR,
            filas_afectadas=len(nuevas),
            ip=ip,
            detalle={
                "operacion": "masiva",
                "rol_id": str(payload.rol_id),
                "contexto": {
                    "materia_id": str(payload.materia_id) if payload.materia_id else None,
                    "carrera_id": str(payload.carrera_id) if payload.carrera_id else None,
                    "cohorte_id": str(payload.cohorte_id) if payload.cohorte_id else None,
                },
            },
        )

        return MasivaResult(creados=len(nuevas), asignaciones=[a.id for a in nuevas])

    # ── F4.5 clonar (RN-12) ──────────────────────────────────────────

    async def clonar_equipo(
        self,
        *,
        tenant_id: UUID,
        payload: ClonarEquipoRequest,
        current_user: CurrentUser,
        ip: str | None = None,
    ) -> ClonarResult:
        hoy = date.today()
        repo = self._repo(tenant_id)

        await self._validar_contexto_fks(
            tenant_id,
            payload.origen.materia_id,
            payload.origen.carrera_id,
            payload.origen.cohorte_id,
        )
        await self._validar_contexto_fks(
            tenant_id,
            payload.destino.materia_id,
            payload.destino.carrera_id,
            payload.destino.cohorte_id,
        )

        vigentes = await repo.list_vigentes_por_contexto(
            materia_id=payload.origen.materia_id,
            carrera_id=payload.origen.carrera_id,
            cohorte_id=payload.origen.cohorte_id,
            today=hoy,
        )

        creadas: list[Asignacion] = []
        omitidas: list[ClonarOmitido] = []

        for a in vigentes:
            ya = await repo.existe_vigente_en_destino(
                usuario_id=a.usuario_id,
                rol_id=a.rol_id,
                materia_id=payload.destino.materia_id,
                carrera_id=payload.destino.carrera_id,
                cohorte_id=payload.destino.cohorte_id,
                today=hoy,
            )
            if ya:
                omitidas.append(ClonarOmitido(usuario_id=a.usuario_id, motivo="ya_vigente_en_destino"))
                continue

            nueva = Asignacion(
                tenant_id=tenant_id,
                usuario_id=a.usuario_id,
                rol_id=a.rol_id,
                materia_id=payload.destino.materia_id,
                carrera_id=payload.destino.carrera_id,
                cohorte_id=payload.destino.cohorte_id,
                comisiones=a.comisiones,
                responsable_id=a.responsable_id,
                desde=payload.desde,
                hasta=payload.hasta,
            )
            self._session.add(nueva)
            creadas.append(nueva)

        await self._session.flush()

        await AuditService(self._session).log(
            current_user=current_user,
            accion=ASIGNACION_MODIFICAR,
            filas_afectadas=len(creadas),
            ip=ip,
            detalle={
                "operacion": "clonar",
                "origen": {
                    "materia_id": str(payload.origen.materia_id) if payload.origen.materia_id else None,
                    "carrera_id": str(payload.origen.carrera_id) if payload.origen.carrera_id else None,
                    "cohorte_id": str(payload.origen.cohorte_id) if payload.origen.cohorte_id else None,
                },
                "destino": {
                    "materia_id": str(payload.destino.materia_id) if payload.destino.materia_id else None,
                    "carrera_id": str(payload.destino.carrera_id) if payload.destino.carrera_id else None,
                    "cohorte_id": str(payload.destino.cohorte_id) if payload.destino.cohorte_id else None,
                },
                "desde": str(payload.desde),
                "hasta": str(payload.hasta) if payload.hasta else None,
                "omitidos": len(omitidas),
            },
        )

        return ClonarResult(creados=len(creadas), omitidos=omitidas)

    # ── F4.6 vigencia bloque ──────────────────────────────────────────

    async def actualizar_vigencia_bloque(
        self,
        *,
        tenant_id: UUID,
        payload: VigenciaBloqueRequest,
        current_user: CurrentUser,
        ip: str | None = None,
    ) -> VigenciaBloqueResult:
        filas = await self._repo(tenant_id).bulk_update_vigencia(
            materia_id=payload.materia_id,
            carrera_id=payload.carrera_id,
            cohorte_id=payload.cohorte_id,
            desde=payload.desde,
            hasta=payload.hasta,
        )
        await self._session.flush()

        await AuditService(self._session).log(
            current_user=current_user,
            accion=ASIGNACION_MODIFICAR,
            filas_afectadas=filas,
            ip=ip,
            detalle={
                "operacion": "vigencia_bloque",
                "contexto": {
                    "materia_id": str(payload.materia_id) if payload.materia_id else None,
                    "carrera_id": str(payload.carrera_id) if payload.carrera_id else None,
                    "cohorte_id": str(payload.cohorte_id) if payload.cohorte_id else None,
                },
                "desde": str(payload.desde),
                "hasta": str(payload.hasta) if payload.hasta else None,
            },
        )

        return VigenciaBloqueResult(filas_afectadas=filas)

    # ── F4.7 exportar CSV ─────────────────────────────────────────────

    async def exportar_csv(self, *, tenant_id: UUID, filtros: EquipoFiltros) -> bytes:
        rows = await self._repo(tenant_id).list_equipo(
            materia_id=filtros.materia_id,
            carrera_id=filtros.carrera_id,
            cohorte_id=filtros.cohorte_id,
            usuario_id=filtros.usuario_id,
            responsable_id=filtros.responsable_id,
            rol=filtros.rol,
            estado_vigencia=filtros.estado_vigencia,
            today=date.today(),
            limit=10_000,
            offset=0,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "apellidos", "nombre", "rol", "materia", "carrera",
            "cohorte", "comisiones", "desde", "hasta", "estado_vigencia",
        ])
        for r in rows:
            writer.writerow([
                r.usuario_apellidos,
                r.usuario_nombre,
                r.rol_nombre,
                r.materia_nombre or "",
                r.carrera_nombre or "",
                r.cohorte_nombre or "",
                str(r.comisiones),
                r.desde.isoformat(),
                r.hasta.isoformat() if r.hasta else "",
                self._vigencia(r.desde, r.hasta),
            ])

        return output.getvalue().encode("utf-8")

    # ── FK validation helper ──────────────────────────────────────────

    async def _validar_contexto_fks(
        self,
        tenant_id: UUID,
        materia_id: UUID | None,
        carrera_id: UUID | None,
        cohorte_id: UUID | None,
    ) -> None:
        if materia_id is not None:
            if await MateriaRepository(self._session, tenant_id).get_by_id(materia_id) is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="materia not found")
        if carrera_id is not None:
            if await CarreraRepository(self._session, tenant_id).get_by_id(carrera_id) is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="carrera not found")
        if cohorte_id is not None:
            if await CohorteRepository(self._session, tenant_id).get_by_id(cohorte_id) is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="cohorte not found")
