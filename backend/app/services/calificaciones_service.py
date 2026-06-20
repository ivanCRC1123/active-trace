"""CalificacionesService — business logic for C-10.

Handles LMS file import, threshold configuration, and data clearing.
All DB access goes through repositories (never direct SQL in services).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import CALIFICACIONES_IMPORTAR
from app.models.asignacion import Asignacion
from app.models.calificacion import OrigenCalificacion
from app.models.entrada_padron import EntradaPadron
from app.models.materia import Materia
from app.models.version_padron import VersionPadron
from app.repositories.calificacion_repository import CalificacionRepository, _derive_aprobado
from app.repositories.umbral_materia_repository import UmbralMateriaRepository
from app.schemas.auth import CurrentUser
from app.schemas.calificaciones import (
    CalificacionResponse,
    GradePreview,
    ImportarCalificacionesRequest,
    ImportarCalificacionesResult,
    UmbralMateriaRequest,
    UmbralMateriaResponse,
    VaciarResult,
)
from app.services.audit_service import AuditService
from app.services.calificaciones_parser import ParsedGradeFile, parse_grade_file, parse_nota_numerica


class CalificacionesService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── File preview (no DB write) ─────────────────────────────────────────────

    async def preview_file(
        self,
        content: bytes,
        filename: str,
    ) -> GradePreview:
        parsed = parse_grade_file(content, filename)
        return GradePreview(
            actividades=[{"nombre": a["nombre"], "tipo": a["tipo"]} for a in parsed["actividades"]],
            total_alumnos=len(parsed["filas"]),
            warnings=parsed["warnings"],
        )

    # ── Import calificaciones ──────────────────────────────────────────────────

    async def importar(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        content: bytes,
        filename: str,
        request: ImportarCalificacionesRequest,
    ) -> ImportarCalificacionesResult:
        asignacion = await self._get_asignacion(
            current_user.user_id, materia_id, cohorte_id, UUID(str(current_user.tenant_id))
        )

        parsed = parse_grade_file(content, filename)
        actividades_sel = set(request.actividades_seleccionadas)
        actividades_validas = {a["nombre"]: a["tipo"] for a in parsed["actividades"] if a["nombre"] in actividades_sel}

        umbral_repo = UmbralMateriaRepository(self._session, str(current_user.tenant_id))
        umbral = await umbral_repo.get_by_asignacion(asignacion.id)
        umbral_pct, valores_aprobatorios = umbral_repo.effective_umbral(umbral)

        email_hash_map = await self._build_email_hash_map(
            materia_id, cohorte_id, UUID(str(current_user.tenant_id))
        )

        cal_repo = CalificacionRepository(self._session, str(current_user.tenant_id))
        importadas = actualizadas = omitidas = 0
        warnings = list(parsed["warnings"])

        from app.core.encryption import hmac_email  # noqa: PLC0415

        for fila in parsed["filas"]:
            email = fila["email"]
            entrada_id = email_hash_map.get(hmac_email(email))
            if entrada_id is None:
                warnings.append(f"Alumno {email!r}: sin entrada en padrón activo — omitido.")
                omitidas += 1
                continue

            for act_name, act_tipo in actividades_validas.items():
                raw = fila["grades"].get(act_name, "").strip()
                nota_numerica = None
                nota_textual = None

                if act_tipo == "numerica":
                    nota_numerica = parse_nota_numerica(raw)
                else:
                    nota_textual = raw if raw else None

                aprobado = _derive_aprobado(nota_numerica, nota_textual, umbral_pct, valores_aprobatorios)

                existing_check = await cal_repo._get_by_key(asignacion.id, entrada_id, act_name)
                await cal_repo.upsert_calificacion(
                    asignacion_id=asignacion.id,
                    entrada_padron_id=entrada_id,
                    materia_id=materia_id,
                    actividad=act_name,
                    nota_numerica=nota_numerica,
                    nota_textual=nota_textual,
                    aprobado=aprobado,
                    origen=OrigenCalificacion.Importado,
                )
                if existing_check is None:
                    importadas += 1
                else:
                    actualizadas += 1

        await self._session.commit()

        await AuditService(self._session).log(
            current_user=current_user,
            accion=CALIFICACIONES_IMPORTAR,
            materia_id=materia_id,
            filas_afectadas=importadas + actualizadas,
            detalle={
                "importadas": importadas,
                "actualizadas": actualizadas,
                "omitidas": omitidas,
                "actividades": list(actividades_validas.keys()),
            },
        )
        await self._session.commit()

        return ImportarCalificacionesResult(
            importadas=importadas,
            actualizadas=actualizadas,
            omitidas=omitidas,
            warnings=warnings,
        )

    # ── List calificaciones ────────────────────────────────────────────────────

    async def list_calificaciones(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
    ) -> list[CalificacionResponse]:
        asignacion = await self._get_asignacion(
            current_user.user_id, materia_id, cohorte_id, UUID(str(current_user.tenant_id))
        )
        cal_repo = CalificacionRepository(self._session, str(current_user.tenant_id))
        rows = await cal_repo.list_by_asignacion(asignacion.id)
        return [
            CalificacionResponse(
                id=r.id,
                asignacion_id=r.asignacion_id,
                entrada_padron_id=r.entrada_padron_id,
                materia_id=r.materia_id,
                actividad=r.actividad,
                nota_numerica=r.nota_numerica,
                nota_textual=r.nota_textual,
                aprobado=r.aprobado,
                origen=r.origen.value,
            )
            for r in rows
        ]

    # ── Umbral ─────────────────────────────────────────────────────────────────

    async def get_umbral(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
    ) -> UmbralMateriaResponse:
        asignacion = await self._get_asignacion(
            current_user.user_id, materia_id, cohorte_id, UUID(str(current_user.tenant_id))
        )
        umbral_repo = UmbralMateriaRepository(self._session, str(current_user.tenant_id))
        umbral = await umbral_repo.get_by_asignacion(asignacion.id)
        pct, valores = umbral_repo.effective_umbral(umbral)
        if umbral is None:
            return UmbralMateriaResponse(
                umbral_pct=pct,
                valores_aprobatorios=valores,
                es_default=True,
            )
        return UmbralMateriaResponse(
            id=umbral.id,
            asignacion_id=umbral.asignacion_id,
            materia_id=umbral.materia_id,
            umbral_pct=umbral.umbral_pct,
            valores_aprobatorios=list(umbral.valores_aprobatorios),
            es_default=False,
        )

    async def upsert_umbral(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        request: UmbralMateriaRequest,
    ) -> UmbralMateriaResponse:
        asignacion = await self._get_asignacion(
            current_user.user_id, materia_id, cohorte_id, UUID(str(current_user.tenant_id))
        )
        umbral_repo = UmbralMateriaRepository(self._session, str(current_user.tenant_id))
        umbral = await umbral_repo.upsert(
            asignacion_id=asignacion.id,
            materia_id=materia_id,
            umbral_pct=request.umbral_pct,
            valores_aprobatorios=request.valores_aprobatorios,
        )

        # Recalculate aprobado for all calificaciones of this asignacion (OQ-C10-2).
        cal_repo = CalificacionRepository(self._session, str(current_user.tenant_id))
        await cal_repo.recalc_aprobado_para_asignacion(
            asignacion_id=asignacion.id,
            umbral_pct=request.umbral_pct,
            valores_aprobatorios=request.valores_aprobatorios,
        )
        await self._session.commit()

        return UmbralMateriaResponse(
            id=umbral.id,
            asignacion_id=umbral.asignacion_id,
            materia_id=umbral.materia_id,
            umbral_pct=umbral.umbral_pct,
            valores_aprobatorios=list(umbral.valores_aprobatorios),
            es_default=False,
        )

    # ── Vaciar (RN-04) ─────────────────────────────────────────────────────────

    async def vaciar(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        perm_scope: str,
    ) -> VaciarResult:
        """Soft-delete calificaciones scoped to (usuario_id × materia_id).

        COORDINADOR (scope='all') can clear any user's data for the materia.
        PROFESOR (scope='own') can only clear their own.
        """
        if perm_scope == "all":
            # COORDINADOR: clear all calificaciones for the materia in this tenant
            count = await self._vaciar_all_for_materia(
                materia_id=materia_id,
                tenant_id=UUID(str(current_user.tenant_id)),
            )
        else:
            cal_repo = CalificacionRepository(self._session, str(current_user.tenant_id))
            count = await cal_repo.vaciar_por_usuario_materia(
                usuario_id=UUID(str(current_user.user_id)),
                materia_id=materia_id,
            )
        await self._session.commit()
        return VaciarResult(eliminadas=count)

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_asignacion(
        self,
        user_id: UUID | str,
        materia_id: UUID,
        cohorte_id: UUID,
        tenant_id: UUID,
    ) -> Asignacion:
        stmt = select(Asignacion).where(
            Asignacion.tenant_id == tenant_id,
            Asignacion.usuario_id == UUID(str(user_id)),
            Asignacion.materia_id == materia_id,
            Asignacion.cohorte_id == cohorte_id,
            Asignacion.deleted_at.is_(None),
        )
        asignacion = (await self._session.execute(stmt)).scalar_one_or_none()
        if asignacion is None:
            raise ValueError("asignacion_not_found")
        return asignacion

    async def _build_email_hash_map(
        self,
        materia_id: UUID,
        cohorte_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, UUID]:
        """Build email → entrada_padron_id map from the active padrón version."""
        from app.core.encryption import hmac_email  # noqa: PLC0415

        version_stmt = select(VersionPadron).where(
            VersionPadron.tenant_id == tenant_id,
            VersionPadron.materia_id == materia_id,
            VersionPadron.cohorte_id == cohorte_id,
            VersionPadron.activa.is_(True),
            VersionPadron.deleted_at.is_(None),
        )
        version = (await self._session.execute(version_stmt)).scalar_one_or_none()
        if version is None:
            return {}

        entry_stmt = select(EntradaPadron).where(
            EntradaPadron.version_id == version.id,
            EntradaPadron.deleted_at.is_(None),
        )
        entries = (await self._session.execute(entry_stmt)).scalars().all()

        # Map email_hash → entrada_id; caller hashes plaintext emails before lookup.
        result: dict[str, UUID] = {}
        for entry in entries:
            result[entry.email_hash] = entry.id

        return result

    async def _vaciar_all_for_materia(
        self,
        materia_id: UUID,
        tenant_id: UUID,
    ) -> int:
        from app.models.calificacion import Calificacion  # noqa: PLC0415
        from sqlalchemy.sql import func  # noqa: PLC0415

        stmt = select(Calificacion).where(
            Calificacion.tenant_id == tenant_id,
            Calificacion.materia_id == materia_id,
            Calificacion.deleted_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        for row in rows:
            row.deleted_at = func.now()
        await self._session.flush()
        return len(rows)
