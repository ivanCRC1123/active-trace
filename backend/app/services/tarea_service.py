"""TareaService — workflow de tareas internas (C-16, Épica 8).

Implementa:
- F8.1 mis_tareas: self-scoped, sin permiso explícito
- F8.2 crear_tarea: scope own (PROFESOR) o all (COORDINADOR/ADMIN)
- F8.2 cambiar_estado: FSM con membership check
- F8.3 list_tareas: global con filtros + scope automático para PROFESOR
- comentarios: membership check para asignado_a / asignado_por / gestores
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import TAREA_ASIGNAR, TAREA_ESTADO_CAMBIAR
from app.models.comentario_tarea import ComentarioTarea
from app.models.tarea import (
    ESTADO_CANCELADA,
    ESTADO_EN_PROGRESO,
    ESTADO_PENDIENTE,
    ESTADO_RESUELTA,
    ESTADOS_TERMINALES,
    Tarea,
)
from app.repositories.asignacion_repository import AsignacionRepository
from app.repositories.comentario_tarea_repository import (
    ComentarioConAutor,
    ComentarioTareaRepository,
)
from app.repositories.tarea_repository import TareaConUsuarios, TareaRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import CurrentUser
from app.schemas.tareas import (
    ComentarioCreateRequest,
    ComentarioResponse,
    MisTareasFiltros,
    TareaCreateRequest,
    TareaFiltros,
    TareaResponse,
    UsuarioResumen,
)
from app.services.audit_service import AuditService

# ── FSM: transiciones válidas ─────────────────────────────────────────────────
# (desde, hacia) -> set de quién puede hacer la transición
# 'asignado_a'  = el asignado puede hacerlo
# 'asignado_por' = quien asignó puede hacerlo
# 'gestores'    = usuarios con tareas_internas:gestionar
_VALID_TRANSITIONS: dict[tuple[str, str], set[str]] = {
    (ESTADO_PENDIENTE,   ESTADO_EN_PROGRESO): {"asignado_a", "gestores"},
    (ESTADO_PENDIENTE,   ESTADO_CANCELADA):   {"asignado_por", "gestores"},
    (ESTADO_EN_PROGRESO, ESTADO_RESUELTA):    {"asignado_a", "gestores"},
    (ESTADO_EN_PROGRESO, ESTADO_CANCELADA):   {"gestores"},
}


def _tcu_to_response(tcu: TareaConUsuarios) -> TareaResponse:
    return TareaResponse(
        id=tcu.id,
        tenant_id=tcu.tenant_id,
        materia_id=tcu.materia_id,
        asignado_a=UsuarioResumen(
            id=tcu.asignado_a_id,
            nombre=tcu.asignado_a_nombre,
            apellidos=tcu.asignado_a_apellidos,
        ),
        asignado_por=UsuarioResumen(
            id=tcu.asignado_por_id,
            nombre=tcu.asignado_por_nombre,
            apellidos=tcu.asignado_por_apellidos,
        ),
        estado=tcu.estado,
        descripcion=tcu.descripcion,
        contexto_id=tcu.contexto_id,
        created_at=tcu.created_at,
        updated_at=tcu.updated_at,
    )


def _cca_to_response(cca: ComentarioConAutor) -> ComentarioResponse:
    return ComentarioResponse(
        id=cca.id,
        tarea_id=cca.tarea_id,
        autor=UsuarioResumen(
            id=cca.autor_id,
            nombre=cca.autor_nombre,
            apellidos=cca.autor_apellidos,
        ),
        texto=cca.texto,
        creado_at=cca.creado_at,
    )


class TareaService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _repo(self, tenant_id: UUID) -> TareaRepository:
        return TareaRepository(self._session, tenant_id)

    def _comentario_repo(self, tenant_id: UUID) -> ComentarioTareaRepository:
        return ComentarioTareaRepository(self._session, tenant_id)

    def _asig_repo(self, tenant_id: UUID) -> AsignacionRepository:
        return AsignacionRepository(self._session, tenant_id)

    def _user_repo(self, tenant_id: UUID) -> UsuarioRepository:
        return UsuarioRepository(self._session, tenant_id)

    def _audit(self) -> AuditService:
        return AuditService(self._session)

    # ── membership check ──────────────────────────────────────────────────────

    def _puede_acceder(
        self,
        current_user: CurrentUser,
        tcu: TareaConUsuarios,
        tiene_gestionar: bool,
    ) -> bool:
        return (
            current_user.user_id == tcu.asignado_a_id
            or current_user.user_id == tcu.asignado_por_id
            or tiene_gestionar
        )

    def _assert_membership(
        self,
        current_user: CurrentUser,
        tcu: TareaConUsuarios,
        tiene_gestionar: bool,
    ) -> None:
        if not self._puede_acceder(current_user, tcu, tiene_gestionar):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin acceso a esta tarea")

    # ── FSM validation ────────────────────────────────────────────────────────

    def _assert_transition(
        self,
        tcu: TareaConUsuarios,
        nuevo_estado: str,
        current_user: CurrentUser,
        tiene_gestionar: bool,
    ) -> None:
        estado_actual = tcu.estado
        if estado_actual in ESTADOS_TERMINALES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"TAREA_ESTADO_TERMINAL: estado '{estado_actual}' es terminal",
            )
        key = (estado_actual, nuevo_estado)
        permitidos = _VALID_TRANSITIONS.get(key)
        if permitidos is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"TAREA_TRANSICION_INVALIDA: '{estado_actual}' → '{nuevo_estado}'",
            )
        # Verificar que el actor tiene el rol adecuado para esta transición
        actor_roles: set[str] = set()
        if current_user.user_id == tcu.asignado_a_id:
            actor_roles.add("asignado_a")
        if current_user.user_id == tcu.asignado_por_id:
            actor_roles.add("asignado_por")
        if tiene_gestionar:
            actor_roles.add("gestores")
        if not actor_roles.intersection(permitidos):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Sin autorización para la transición '{estado_actual}' → '{nuevo_estado}'",
            )

    # ── F8.1 mis_tareas ───────────────────────────────────────────────────────

    async def mis_tareas(
        self,
        *,
        tenant_id: UUID,
        usuario_id: UUID,
        filtros: MisTareasFiltros,
    ) -> list[TareaResponse]:
        rows = await self._repo(tenant_id).list_by_asignado_a(usuario_id, filtros)
        return [_tcu_to_response(r) for r in rows]

    # ── F8.2 crear_tarea ─────────────────────────────────────────────────────

    async def crear_tarea(
        self,
        *,
        tenant_id: UUID,
        payload: TareaCreateRequest,
        current_user: CurrentUser,
        scope: str | None,
        ip: str | None = None,
    ) -> TareaResponse:
        # Verificar asignado_a en tenant
        user_repo = self._user_repo(tenant_id)
        dest = await user_repo.get_by_id(payload.asignado_a)
        if dest is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="asignado_a no existe en este tenant",
            )

        # Verificar materia si se proporciona
        if payload.materia_id is not None:
            from app.repositories.materia_repository import MateriaRepository  # noqa: PLC0415
            mat_repo = MateriaRepository(self._session, tenant_id)
            mat = await mat_repo.get_by_id(payload.materia_id)
            if mat is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="materia_id no existe en este tenant",
                )

        # Scope check para PROFESOR (own)
        if scope == "own":
            if payload.materia_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="PROFESOR requiere materia_id para crear tareas",
                )
            asig_repo = self._asig_repo(tenant_id)
            vigente = await asig_repo.existe_vigente_en_materia(
                usuario_id=current_user.user_id,
                materia_id=payload.materia_id,
                today=date.today(),
            )
            if not vigente:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sin asignación vigente en esa materia",
                )

        tarea = Tarea(
            tenant_id=tenant_id,
            materia_id=payload.materia_id,
            asignado_a=payload.asignado_a,
            asignado_por=current_user.user_id,
            descripcion=payload.descripcion,
            contexto_id=payload.contexto_id,
        )
        created = await self._repo(tenant_id).create(tarea)
        await self._session.flush()

        await self._audit().log(
            current_user=current_user,
            accion=TAREA_ASIGNAR,
            detalle={
                "tarea_id": str(created.id),
                "asignado_a": str(payload.asignado_a),
                "materia_id": str(payload.materia_id) if payload.materia_id else None,
                "estado_inicial": "Pendiente",
            },
            filas_afectadas=1,
            ip=ip,
            materia_id=payload.materia_id,
        )

        tcu = await self._repo(tenant_id).get_con_usuarios(created.id)
        if tcu is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return _tcu_to_response(tcu)

    # ── get_tarea (detalle) ───────────────────────────────────────────────────

    async def get_tarea(
        self,
        *,
        tarea_id: UUID,
        tenant_id: UUID,
        current_user: CurrentUser,
        tiene_gestionar: bool,
    ) -> TareaResponse:
        tcu = await self._repo(tenant_id).get_con_usuarios(tarea_id)
        if tcu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
        self._assert_membership(current_user, tcu, tiene_gestionar)
        return _tcu_to_response(tcu)

    # ── cambiar_estado (FSM) ──────────────────────────────────────────────────

    async def cambiar_estado(
        self,
        *,
        tarea_id: UUID,
        tenant_id: UUID,
        nuevo_estado: str,
        current_user: CurrentUser,
        tiene_gestionar: bool,
        ip: str | None = None,
    ) -> TareaResponse:
        tcu = await self._repo(tenant_id).get_con_usuarios(tarea_id)
        if tcu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")

        self._assert_membership(current_user, tcu, tiene_gestionar)
        self._assert_transition(tcu, nuevo_estado, current_user, tiene_gestionar)

        estado_anterior = tcu.estado
        raw = await self._repo(tenant_id).get_raw(tarea_id)
        if raw is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        raw.estado = nuevo_estado
        await self._session.flush()

        await self._audit().log(
            current_user=current_user,
            accion=TAREA_ESTADO_CAMBIAR,
            detalle={
                "tarea_id": str(tarea_id),
                "estado_anterior": estado_anterior,
                "estado_nuevo": nuevo_estado,
            },
            filas_afectadas=1,
            ip=ip,
            materia_id=tcu.materia_id,
        )

        updated = await self._repo(tenant_id).get_con_usuarios(tarea_id)
        if updated is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return _tcu_to_response(updated)

    # ── F8.3 list_tareas (admin global) ──────────────────────────────────────

    async def list_tareas(
        self,
        *,
        tenant_id: UUID,
        filtros: TareaFiltros,
        current_user: CurrentUser,
        scope: str | None,
    ) -> list[TareaResponse]:
        scope_user_id = current_user.user_id if scope == "own" else None
        rows = await self._repo(tenant_id).list_tareas(filtros, scope_user_id=scope_user_id)
        return [_tcu_to_response(r) for r in rows]

    # ── comentarios ───────────────────────────────────────────────────────────

    async def agregar_comentario(
        self,
        *,
        tarea_id: UUID,
        tenant_id: UUID,
        payload: ComentarioCreateRequest,
        current_user: CurrentUser,
        tiene_gestionar: bool,
    ) -> ComentarioResponse:
        tcu = await self._repo(tenant_id).get_con_usuarios(tarea_id)
        if tcu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
        self._assert_membership(current_user, tcu, tiene_gestionar)

        comentario = ComentarioTarea(
            tenant_id=tenant_id,
            tarea_id=tarea_id,
            autor_id=current_user.user_id,
            texto=payload.texto,
        )
        comentario_repo = self._comentario_repo(tenant_id)
        created = await comentario_repo.create(comentario)
        await self._session.flush()

        rows = await comentario_repo.list_by_tarea(tarea_id)
        for r in rows:
            if r.id == created.id:
                return _cca_to_response(r)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    async def list_comentarios(
        self,
        *,
        tarea_id: UUID,
        tenant_id: UUID,
        current_user: CurrentUser,
        tiene_gestionar: bool,
    ) -> list[ComentarioResponse]:
        tcu = await self._repo(tenant_id).get_con_usuarios(tarea_id)
        if tcu is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
        self._assert_membership(current_user, tcu, tiene_gestionar)

        rows = await self._comentario_repo(tenant_id).list_by_tarea(tarea_id)
        return [_cca_to_response(r) for r in rows]
