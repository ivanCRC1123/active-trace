"""UsuarioRepository — extends UserRepository with asignacion-vigencia check."""

from datetime import date
from uuid import UUID

from sqlalchemy import select, or_

from app.models.user import User
from app.repositories.user_repository import UserRepository


class UsuarioRepository(UserRepository):
    """Extends UserRepository with asignacion-vigencia check for safe deletion."""

    async def has_asignaciones_vigentes(self, usuario_id: UUID) -> bool:
        from app.models.asignacion import Asignacion  # noqa: PLC0415 — circular import guard
        today = date.today()
        stmt = select(Asignacion).where(
            Asignacion.tenant_id == self._tenant_id,
            Asignacion.usuario_id == usuario_id,
            Asignacion.deleted_at.is_(None),
            Asignacion.desde <= today,
            or_(Asignacion.hasta.is_(None), Asignacion.hasta >= today),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None
