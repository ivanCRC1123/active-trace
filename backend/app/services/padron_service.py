"""PadronService — business logic for padrón ingesta (C-09).

Handles file import (xlsx/csv), Moodle WS sync, versioned upsert,
auto-link to User by email_hash, and soft-delete (vaciar).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.audit_codes import PADRON_CARGAR
from app.core.encryption import hmac_email
from app.integrations.moodle_ws import MoodleWSClientProtocol
from app.models.entrada_padron import EntradaPadron
from app.models.materia import Materia
from app.models.user import User
from app.models.version_padron import VersionPadron
from app.repositories.entrada_padron_repository import EntradaPadronRepository
from app.repositories.version_padron_repository import VersionPadronRepository
from app.schemas.auth import CurrentUser
from app.schemas.padron import (
    EntradaPadronResponse,
    PadronConEntradas,
    PadronImportResult,
    PadronPreview,
    PadronPreviewEntry,
    VersionPadronResponse,
)
from app.services.audit_service import AuditService
from app.services.padron_parser import PadronRow, parse_padron_file


class PadronService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Public API ─────────────────────────────────────────────────────────────

    async def import_from_file(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        content: bytes,
        filename: str,
        preview: bool,
    ) -> PadronImportResult | PadronPreview:
        rows, warnings = parse_padron_file(content, filename)

        if preview:
            return await self._build_preview(
                rows=rows,
                warnings=warnings,
                tenant_id=current_user.tenant_id,
            )

        await self._assert_materia_cohorte_in_tenant(
            materia_id, cohorte_id, current_user.tenant_id
        )
        return await self._do_import(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            rows=rows,
            warnings=warnings,
        )

    async def import_from_moodle(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        moodle_client: MoodleWSClientProtocol,
    ) -> PadronImportResult:
        from app.core.config import settings  # noqa: PLC0415

        if not settings.MOODLE_BASE_URL:
            raise ValueError("moodle_no_configurado")

        course_id = await self._get_moodle_course_id(materia_id, current_user.tenant_id)
        if course_id is None:
            raise ValueError("materia_sin_moodle_course_id")

        await self._assert_materia_cohorte_in_tenant(
            materia_id, cohorte_id, current_user.tenant_id
        )

        participants = await moodle_client.get_participants(course_id)
        rows: list[PadronRow] = []
        warnings: list[str] = []
        seen: set[str] = set()
        for p in participants:
            email = (p.get("email") or "").strip().lower()
            if not email or not p.get("nombre") or not p.get("apellidos"):
                warnings.append(f"Participante Moodle ignorado: datos incompletos ({p})")
                continue
            if email in seen:
                warnings.append(f"Email duplicado en Moodle: {email}")
                continue
            seen.add(email)
            rows.append(
                PadronRow(
                    nombre=p["nombre"],
                    apellidos=p["apellidos"],
                    email=email,
                    comision=p.get("comision"),
                    regional=p.get("regional"),
                )
            )

        return await self._do_import(
            materia_id=materia_id,
            cohorte_id=cohorte_id,
            current_user=current_user,
            rows=rows,
            warnings=warnings,
        )

    async def get_padron_activo(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        tenant_id: UUID,
    ) -> PadronConEntradas | None:
        version_repo = VersionPadronRepository(self._session, tenant_id)
        version = await version_repo.get_active(materia_id, cohorte_id)
        if version is None:
            return None

        entrada_repo = EntradaPadronRepository(self._session, tenant_id)
        entradas = await entrada_repo.list_by_version(version.id)

        entrada_responses = [self._to_entrada_response(e) for e in entradas]
        vinculadas = sum(1 for e in entrada_responses if e.vinculado)

        return PadronConEntradas(
            version=self._to_version_response(version, len(entrada_responses), vinculadas),
            entradas=entrada_responses,
        )

    async def vaciar(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        perm_scope: str,
    ) -> None:
        version_repo = VersionPadronRepository(self._session, current_user.tenant_id)
        version = await version_repo.get_active(materia_id, cohorte_id)
        if version is None:
            raise ValueError("padron_not_found")

        if perm_scope == "own" and version.cargado_por != current_user.user_id:
            raise ValueError("padron_no_autorizado")

        version.activa = False
        version.deleted_at = func.now()
        await self._session.flush()

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _do_import(
        self,
        *,
        materia_id: UUID,
        cohorte_id: UUID,
        current_user: CurrentUser,
        rows: list[PadronRow],
        warnings: list[str],
    ) -> PadronImportResult:
        tenant_id = current_user.tenant_id
        version_repo = VersionPadronRepository(self._session, tenant_id)
        entrada_repo = EntradaPadronRepository(self._session, tenant_id)

        # Deactivate previous version in same transaction
        await version_repo.deactivate_current(materia_id, cohorte_id)

        # Create new active version
        version = await version_repo.create(
            VersionPadron(
                materia_id=materia_id,
                cohorte_id=cohorte_id,
                cargado_por=current_user.user_id,
                activa=True,
            )
        )

        # Build and bulk-insert entries
        entradas: list[EntradaPadron] = []
        for row in rows:
            usuario_id = await self._resolve_usuario_id(row["email"], tenant_id)
            entradas.append(
                EntradaPadron(
                    version_id=version.id,
                    usuario_id=usuario_id,
                    nombre=row["nombre"],
                    apellidos=row["apellidos"],
                    email_cifrado=row["email"],   # EncryptedString TypeDecorator encrypts on write
                    email_hash=hmac_email(row["email"]),
                    comision=row.get("comision"),
                    regional=row.get("regional"),
                )
            )

        await entrada_repo.bulk_create(entradas)

        vinculadas = sum(1 for e in entradas if e.usuario_id is not None)

        # Audit
        audit_svc = AuditService(self._session)
        await audit_svc.log(
            current_user=current_user,
            accion=PADRON_CARGAR,
            detalle={
                "version_id": str(version.id),
                "materia_id": str(materia_id),
                "cohorte_id": str(cohorte_id),
                "total_entradas": len(entradas),
                "entradas_vinculadas": vinculadas,
            },
            filas_afectadas=len(entradas),
            materia_id=materia_id,
        )

        return PadronImportResult(
            version=self._to_version_response(version, len(entradas), vinculadas),
            total_importadas=len(entradas),
            entradas_vinculadas=vinculadas,
            advertencias=warnings,
        )

    async def _build_preview(
        self,
        *,
        rows: list[PadronRow],
        warnings: list[str],
        tenant_id: UUID,
    ) -> PadronPreview:
        entries: list[PadronPreviewEntry] = []
        vinculados = 0
        for row in rows:
            uid = await self._resolve_usuario_id(row["email"], tenant_id)
            linked = uid is not None
            if linked:
                vinculados += 1
            entries.append(
                PadronPreviewEntry(
                    nombre=row["nombre"],
                    apellidos=row["apellidos"],
                    comision=row.get("comision"),
                    regional=row.get("regional"),
                    vinculado=linked,
                )
            )
        return PadronPreview(
            total=len(entries),
            vinculados=vinculados,
            advertencias=warnings,
            entradas=entries,
        )

    async def _resolve_usuario_id(self, email: str, tenant_id: UUID) -> UUID | None:
        """Look up a User by email_hash in the same tenant. Returns None if not found."""
        h = hmac_email(email)
        result = await self._session.execute(
            select(User.id).where(
                User.tenant_id == tenant_id,
                User.email_hash == h,
                User.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _get_moodle_course_id(self, materia_id: UUID, tenant_id: UUID) -> str | None:
        result = await self._session.execute(
            select(Materia.moodle_course_id).where(
                Materia.id == materia_id,
                Materia.tenant_id == tenant_id,
                Materia.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _assert_materia_cohorte_in_tenant(
        self, materia_id: UUID, cohorte_id: UUID, tenant_id: UUID
    ) -> None:
        from app.models.cohorte import Cohorte  # noqa: PLC0415

        mat = await self._session.execute(
            select(Materia.id).where(
                Materia.id == materia_id,
                Materia.tenant_id == tenant_id,
                Materia.deleted_at.is_(None),
            )
        )
        if mat.scalar_one_or_none() is None:
            raise ValueError("materia_not_found")

        coh = await self._session.execute(
            select(Cohorte.id).where(
                Cohorte.id == cohorte_id,
                Cohorte.tenant_id == tenant_id,
                Cohorte.deleted_at.is_(None),
            )
        )
        if coh.scalar_one_or_none() is None:
            raise ValueError("cohorte_not_found")

    @staticmethod
    def _to_version_response(
        v: VersionPadron, total_entradas: int, entradas_vinculadas: int
    ) -> VersionPadronResponse:
        return VersionPadronResponse(
            id=v.id,
            tenant_id=v.tenant_id,
            materia_id=v.materia_id,
            cohorte_id=v.cohorte_id,
            cargado_por=v.cargado_por,
            cargado_at=v.cargado_at,
            activa=v.activa,
            total_entradas=total_entradas,
            entradas_vinculadas=entradas_vinculadas,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )

    @staticmethod
    def _to_entrada_response(e: EntradaPadron) -> EntradaPadronResponse:
        return EntradaPadronResponse(
            id=e.id,
            version_id=e.version_id,
            tenant_id=e.tenant_id,
            usuario_id=e.usuario_id,
            nombre=e.nombre,
            apellidos=e.apellidos,
            email=e.email_cifrado,  # TypeDecorator has already decrypted this on read
            comision=e.comision,
            regional=e.regional,
            vinculado=e.usuario_id is not None,
            created_at=e.created_at,
            updated_at=e.updated_at,
        )
