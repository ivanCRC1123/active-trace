"""ComunicacionService — C-12 comunicaciones-cola-worker.

Lógica de negocio: preview, crear lote, aprobar, cancelar.
No emite SQL directamente — todo va por ComunicacionRepository.
No accede a Tenant ni EntradaPadron directamente — usa helpers privados con queries mínimas.

RN-17 (simplificación documentada):
  Aprobación requerida cuando tenant.requiere_aprobacion_comunicacion=True
  Y (scope='all' OR n_destinatarios > settings.COMUNICACION_UMBRAL_MASIVO).
  El check completo de 'contexto propio' (¿todos los destinatarios pertenecen
  al padrón de asignaciones del usuario?) está simplificado a scope='all'.
  TODO: implementar check completo de contexto propio en C-22 o cambio posterior.
"""
from __future__ import annotations

import string
from datetime import timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import COMUNICACION_APROBAR, COMUNICACION_ENVIAR
from app.core.config import settings
from app.models.comunicacion import EstadoComunicacion
from app.models.entrada_padron import EntradaPadron
from app.models.materia import Materia
from app.models.tenant import Tenant
from app.repositories.comunicacion_repository import ComunicacionRepository
from app.schemas.auth import CurrentUser
from app.schemas.comunicaciones import (
    AprobacionResponse,
    CancelacionIndividualResponse,
    CancelacionLoteResponse,
    ComunicacionItem,
    ComunicacionListResponse,
    LoteCreado,
    LoteDetalle,
    PreviewItem,
    PreviewResponse,
    ResumenEstados,
)
from app.services.audit_service import AuditService


class ComunicacionService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _repo(self, tenant_id: str) -> ComunicacionRepository:
        return ComunicacionRepository(self._session, tenant_id)

    # ── F3.1 — Preview (RN-16) ────────────────────────────────────────────────

    async def preview(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        asunto_template: str,
        cuerpo_template: str,
        destinatarios: list[UUID],
        current_user: CurrentUser,
    ) -> PreviewResponse:
        """Renderiza el mensaje por destinatario SIN persistir nada (RN-16)."""
        materia_nombre = await self._get_materia_nombre(materia_id, str(current_user.tenant_id))
        entradas = await self._get_entradas(destinatarios, str(current_user.tenant_id))

        items = []
        for ep in entradas:
            ctx = self._build_template_ctx(ep, materia_nombre)
            items.append(
                PreviewItem(
                    entrada_padron_id=ep.id,
                    nombre=ep.nombre,
                    apellidos=ep.apellidos,
                    asunto_renderizado=_render(asunto_template, ctx),
                    cuerpo_renderizado=_render(cuerpo_template, ctx),
                )
            )
        return PreviewResponse(items=items, total=len(items))

    # ── F3.2 — Crear lote ─────────────────────────────────────────────────────

    async def crear_lote(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        asunto_template: str,
        cuerpo_template: str,
        destinatarios: list[UUID],
        current_user: CurrentUser,
        scope: str | None,
    ) -> LoteCreado:
        """Encola N comunicaciones con el mismo lote_id.

        Si requiere aprobación → quedan en PENDIENTE.
        Si no → pasan directamente a ENVIANDO (sin paso humano).
        """
        tenant_id = str(current_user.tenant_id)
        tenant = await self._get_tenant(tenant_id)
        materia_nombre = await self._get_materia_nombre(materia_id, tenant_id)
        entradas = await self._get_entradas(destinatarios, tenant_id)

        if not entradas:
            raise ValueError("sin_destinatarios_validos")

        n = len(entradas)
        aprobacion = _necesita_aprobacion(
            tenant_requiere=tenant.requiere_aprobacion_comunicacion,
            scope=scope,
            n_destinatarios=n,
        )
        estado_inicial = (
            EstadoComunicacion.PENDIENTE if aprobacion else EstadoComunicacion.ENVIANDO
        )
        lote_id = uuid4()

        rows = []
        for ep in entradas:
            ctx = self._build_template_ctx(ep, materia_nombre)
            rows.append({
                "enviado_por": current_user.user_id,
                "materia_id": materia_id,
                "entrada_padron_id": ep.id,
                "destinatario": ep.email_cifrado,  # EncryptedString descifra/re-cifra
                "asunto": _render(asunto_template, ctx),
                "cuerpo": _render(cuerpo_template, ctx),
                "estado": estado_inicial.value,
                "lote_id": lote_id,
            })

        repo = self._repo(tenant_id)
        await repo.bulk_create(rows)

        await AuditService(self._session).log(
            current_user=current_user,
            accion=COMUNICACION_ENVIAR,
            detalle={
                "lote_id": str(lote_id),
                "materia_id": str(materia_id),
                "n_destinatarios": n,
                "estado_inicial": estado_inicial.value,
                "requiere_aprobacion": aprobacion,
            },
            filas_afectadas=n,
        )

        return LoteCreado(
            lote_id=lote_id,
            total_encolados=n,
            requiere_aprobacion=aprobacion,
        )

    # ── F3.3 — Aprobar lote (FL-04 Parte B) ──────────────────────────────────

    async def aprobar_lote(
        self,
        lote_id: UUID,
        current_user: CurrentUser,
    ) -> AprobacionResponse:
        tenant_id = str(current_user.tenant_id)
        repo = self._repo(tenant_id)

        aprobadas, ignoradas = await repo.aprobar_lote(
            lote_id=lote_id,
            aprobado_por=current_user.user_id,
        )
        if aprobadas == 0 and ignoradas == 0:
            raise ValueError("lote_not_found")

        await AuditService(self._session).log(
            current_user=current_user,
            accion=COMUNICACION_APROBAR,
            detalle={"lote_id": str(lote_id), "aprobadas": aprobadas},
            filas_afectadas=aprobadas,
        )

        return AprobacionResponse(
            lote_id=lote_id,
            aprobadas=aprobadas,
            ignoradas=ignoradas,
        )

    # ── Cancelar lote ─────────────────────────────────────────────────────────

    async def cancelar_lote(
        self,
        lote_id: UUID,
        current_user: CurrentUser,
    ) -> CancelacionLoteResponse:
        tenant_id = str(current_user.tenant_id)
        repo = self._repo(tenant_id)
        canceladas = await repo.cancelar_lote(lote_id=lote_id)
        return CancelacionLoteResponse(lote_id=lote_id, canceladas=canceladas)

    # ── Cancelar individual ───────────────────────────────────────────────────

    async def cancelar_individual(
        self,
        com_id: UUID,
        current_user: CurrentUser,
    ) -> CancelacionIndividualResponse:
        tenant_id = str(current_user.tenant_id)
        repo = self._repo(tenant_id)
        com = await repo.get_by_id(com_id)
        if com is None:
            raise ValueError("comunicacion_not_found")
        estado_previo = com.estado
        updated = await repo.set_estado(com.id, EstadoComunicacion.CANCELADO)
        return CancelacionIndividualResponse(
            id=com.id,
            estado_previo=estado_previo,
            estado_nuevo=updated.estado,
        )

    # ── Detalle de lote ───────────────────────────────────────────────────────

    async def get_lote(
        self,
        lote_id: UUID,
        current_user: CurrentUser,
    ) -> LoteDetalle:
        tenant_id = str(current_user.tenant_id)
        repo = self._repo(tenant_id)
        coms = await repo.list_by_lote(lote_id)
        if not coms:
            raise ValueError("lote_not_found")

        estado_counts = repo.resumen_estados(coms)
        resumen = ResumenEstados(
            PENDIENTE=estado_counts.get("PENDIENTE", 0),
            ENVIANDO=estado_counts.get("ENVIANDO", 0),
            ENVIADO=estado_counts.get("ENVIADO", 0),
            ERROR=estado_counts.get("ERROR", 0),
            CANCELADO=estado_counts.get("CANCELADO", 0),
        )

        # Obtener nombre/apellidos de entrada_padron para los items que la tienen
        ep_ids = [c.entrada_padron_id for c in coms if c.entrada_padron_id]
        ep_map = await self._get_ep_map(ep_ids, tenant_id)

        items = [
            ComunicacionItem(
                id=c.id,
                entrada_padron_id=c.entrada_padron_id,
                nombre=ep_map.get(c.entrada_padron_id, {}).get("nombre") if c.entrada_padron_id else None,
                apellidos=ep_map.get(c.entrada_padron_id, {}).get("apellidos") if c.entrada_padron_id else None,
                estado=c.estado,
                enviado_at=c.enviado_at,
                aprobado_at=c.aprobado_at,
            )
            for c in coms
        ]

        return LoteDetalle(
            lote_id=lote_id,
            materia_id=coms[0].materia_id,
            enviado_por=coms[0].enviado_por,
            resumen_estados=resumen,
            items=items,
        )

    # ── Listado de comunicaciones ─────────────────────────────────────────────

    async def list_comunicaciones(
        self,
        current_user: CurrentUser,
        scope: str | None,
        *,
        lote_id: UUID | None = None,
        estado: str | None = None,
        materia_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ComunicacionListResponse:
        tenant_id = str(current_user.tenant_id)
        repo = self._repo(tenant_id)

        if scope == "all":
            coms, total = await repo.list_tenant(
                lote_id=lote_id, estado=estado, materia_id=materia_id,
                limit=limit, offset=offset,
            )
        else:
            coms, total = await repo.list_by_usuario(
                usuario_id=current_user.user_id,
                lote_id=lote_id, estado=estado, materia_id=materia_id,
                limit=limit, offset=offset,
            )

        ep_ids = [c.entrada_padron_id for c in coms if c.entrada_padron_id]
        ep_map = await self._get_ep_map(ep_ids, tenant_id)

        items = [
            ComunicacionItem(
                id=c.id,
                entrada_padron_id=c.entrada_padron_id,
                nombre=ep_map.get(c.entrada_padron_id, {}).get("nombre") if c.entrada_padron_id else None,
                apellidos=ep_map.get(c.entrada_padron_id, {}).get("apellidos") if c.entrada_padron_id else None,
                estado=c.estado,
                enviado_at=c.enviado_at,
                aprobado_at=c.aprobado_at,
            )
            for c in coms
        ]

        return ComunicacionListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    # ── Helpers privados ──────────────────────────────────────────────────────

    async def _get_tenant(self, tenant_id: str) -> Tenant:
        stmt = select(Tenant).where(
            Tenant.id == UUID(tenant_id),
            Tenant.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        t = result.scalar_one_or_none()
        if t is None:
            raise ValueError("tenant_not_found")
        return t

    async def _get_materia_nombre(self, materia_id: UUID, tenant_id: str) -> str:
        stmt = select(Materia.nombre).where(
            Materia.id == materia_id,
            Materia.tenant_id == UUID(tenant_id),
            Materia.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        nombre = result.scalar_one_or_none()
        if nombre is None:
            raise ValueError("materia_not_found")
        return nombre

    async def _get_entradas(
        self, ep_ids: list[UUID], tenant_id: str
    ) -> list[EntradaPadron]:
        """Resuelve EntradaPadron por ID. Solo retorna las que pertenecen al tenant."""
        if not ep_ids:
            return []
        stmt = select(EntradaPadron).where(
            EntradaPadron.id.in_(ep_ids),
            EntradaPadron.tenant_id == UUID(tenant_id),
            EntradaPadron.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def _get_ep_map(
        self, ep_ids: list[UUID], tenant_id: str
    ) -> dict[UUID, dict]:
        """Mapa {entrada_padron_id: {nombre, apellidos}} para armar respuestas sin PII."""
        if not ep_ids:
            return {}
        stmt = select(
            EntradaPadron.id,
            EntradaPadron.nombre,
            EntradaPadron.apellidos,
        ).where(
            EntradaPadron.id.in_(ep_ids),
            EntradaPadron.tenant_id == UUID(tenant_id),
        )
        result = await self._session.execute(stmt)
        return {row.id: {"nombre": row.nombre, "apellidos": row.apellidos} for row in result}

    @staticmethod
    def _build_template_ctx(ep: EntradaPadron, materia_nombre: str) -> dict:
        return {
            "nombre": ep.nombre,
            "apellidos": ep.apellidos,
            "materia": materia_nombre,
        }


# ── Funciones puras ───────────────────────────────────────────────────────────


def _render(template: str, ctx: dict) -> str:
    """Renderiza una plantilla con variables {nombre}, {apellidos}, {materia}.

    Usa string.Formatter con default_map para que variables desconocidas
    queden en blanco en lugar de lanzar KeyError.
    """
    try:
        return string.Formatter().vformat(template, (), _DefaultDict(ctx))
    except (ValueError, TypeError):
        return template


class _DefaultDict(dict):
    """Dict que devuelve '' para claves faltantes, evitando KeyError en format_map."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _necesita_aprobacion(
    tenant_requiere: bool,
    scope: str | None,
    n_destinatarios: int,
) -> bool:
    """Determina si el lote requiere aprobación humana (RN-17 simplificado).

    Lógica:
      1. Si tenant.requiere_aprobacion_comunicacion=False → nunca.
      2. scope='all' → fuera del contexto propio → siempre requiere aprobación.
      3. scope='own' pero masivo (>COMUNICACION_UMBRAL_MASIVO) → requiere.
      4. scope='own' y no masivo → no requiere (el docente envía a sus propios alumnos).

    SIMPLIFICACIÓN RN-17: El check de 'contexto propio' está simplificado a scope='own'.
    El check completo (¿todos los destinatarios pertenecen al padrón de asignaciones del
    usuario?) está pendiente para C-22 / iteración posterior.
    """
    if not tenant_requiere:
        return False
    if scope == "all":
        return True
    # scope='own' — check de masividad como salvaguarda adicional
    return n_destinatarios > settings.COMUNICACION_UMBRAL_MASIVO
