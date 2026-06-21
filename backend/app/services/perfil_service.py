"""PerfilService — edición del perfil propio (C-20 F11.1).

Self-only: el servicio opera siempre sobre current_user.id.
Ninguna vía permite modificar el perfil de otro usuario.

Reglas críticas:
- Email: actualización atómica de email_cifrado + email_hash.
- CUIL: nunca escrito por este servicio (readonly para el usuario).
- PII: nunca aparece en el detalle del AuditLog.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_codes import PERFIL_ACTUALIZAR
from app.core.encryption import hmac_email
from app.models.user import User
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.auth import CurrentUser
from app.schemas.perfil import PerfilUpdate
from app.services.audit_service import AuditService

# Campos que contienen PII y nunca deben incluirse en el detalle del audit.
_PII_FIELDS = frozenset({"email", "dni", "cbu", "alias_cbu", "cuil"})

# Mapeo de nombre de campo PerfilUpdate → columna en User ORM.
_COLUMN_MAP: dict[str, str] = {
    "nombre": "nombre",
    "apellidos": "apellidos",
    "sexo": "sexo",
    "dni": "dni_cifrado",
    "cbu": "cbu_cifrado",
    "alias_cbu": "alias_cbu_cifrado",
    "banco": "banco",
    "regional": "regional",
    "legajo_profesional": "legajo_profesional",
    "facturador": "facturador",
}


class PerfilService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _repo(self, tenant_id: UUID) -> UsuarioRepository:
        return UsuarioRepository(self._session, tenant_id)

    async def get_propio(self, current_user: CurrentUser) -> User:
        """Retorna el registro User del usuario autenticado."""
        user = await self._repo(current_user.tenant_id).get_by_id(current_user.user_id)
        if user is None:
            raise ValueError("user not found")
        return user

    async def update_propio(
        self,
        current_user: CurrentUser,
        data: PerfilUpdate,
    ) -> User:
        """Aplica los campos de PerfilUpdate al usuario autenticado.

        - email: actualiza email_cifrado + email_hash atómicamente; valida unicidad.
        - PII restante: EncryptedString TypeDecorator cifra en INSERT/UPDATE.
        - cuil/legajo: ausentes del schema → nunca escritos aquí.
        """
        repo = self._repo(current_user.tenant_id)
        user = await repo.get_by_id(current_user.user_id)
        if user is None:
            raise ValueError("user not found")

        payload = data.model_dump(exclude_none=True)
        campos_modificados: list[str] = []

        # ── Email: ruta especial (dual-write cifrado + blind index) ──────────
        if "email" in payload:
            new_email: str = str(payload.pop("email"))
            normalized = new_email.strip().lower()
            new_hash = hmac_email(normalized)

            # Verificar unicidad en tenant (excluir al propio usuario)
            stmt = select(User).where(
                User.tenant_id == current_user.tenant_id,
                User.email_hash == new_hash,
                User.deleted_at.is_(None),
            )
            result = await self._session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None and existing.id != current_user.user_id:
                raise ValueError("email_ya_registrado")

            # Solo actualizar si cambia el hash (evita audit innecesario).
            # Se pasa plaintext: EncryptedString TypeDecorator cifra en process_bind_param.
            if new_hash != user.email_hash:
                user.email_cifrado = normalized
                user.email_hash = new_hash
                campos_modificados.append("email")

        # ── Resto de campos vía _COLUMN_MAP ──────────────────────────────────
        for field_name, value in payload.items():
            col_name = _COLUMN_MAP.get(field_name)
            if col_name is None:
                continue
            setattr(user, col_name, value)
            campos_modificados.append(field_name)

        if campos_modificados:
            await self._session.flush()
            await self._session.refresh(user)

            # Auditoría: nombres de campos modificados, nunca valores PII.
            detalle: dict = {"campos_modificados": campos_modificados}
            if "email" in campos_modificados:
                detalle["cambio_email"] = True

            await AuditService(self._session).log(
                current_user=current_user,
                accion=PERFIL_ACTUALIZAR,
                detalle=detalle,
                filas_afectadas=1,
            )

        return user
