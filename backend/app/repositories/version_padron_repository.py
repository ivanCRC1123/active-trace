"""VersionPadronRepository — tenant-scoped queries for VersionPadron."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select, update

from app.models.version_padron import VersionPadron
from app.repositories.base import BaseRepository


class VersionPadronRepository(BaseRepository[VersionPadron]):
    @property
    def model_class(self) -> type[VersionPadron]:
        return VersionPadron

    async def get_active(self, materia_id: UUID, cohorte_id: UUID) -> VersionPadron | None:
        """Return the single active version for (materia_id, cohorte_id), or None."""
        stmt = select(VersionPadron).where(
            VersionPadron.tenant_id == self._tenant_id,
            VersionPadron.materia_id == materia_id,
            VersionPadron.cohorte_id == cohorte_id,
            VersionPadron.activa.is_(True),
            VersionPadron.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def deactivate_current(self, materia_id: UUID, cohorte_id: UUID) -> None:
        """Set activa=False on the current active version (if any).

        Must be called inside the same transaction that creates the new version.
        """
        stmt = (
            update(VersionPadron)
            .where(
                VersionPadron.tenant_id == self._tenant_id,
                VersionPadron.materia_id == materia_id,
                VersionPadron.cohorte_id == cohorte_id,
                VersionPadron.activa.is_(True),
                VersionPadron.deleted_at.is_(None),
            )
            .values(activa=False)
        )
        await self._session.execute(stmt)

    async def list_by_materia(self, materia_id: UUID) -> Sequence[VersionPadron]:
        """Return all versions (active + inactive) for a materia in this tenant."""
        stmt = select(VersionPadron).where(
            VersionPadron.tenant_id == self._tenant_id,
            VersionPadron.materia_id == materia_id,
            VersionPadron.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
