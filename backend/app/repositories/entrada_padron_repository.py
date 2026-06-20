"""EntradaPadronRepository — tenant-scoped queries for EntradaPadron."""

from __future__ import annotations

from typing import Sequence
from uuid import UUID

from sqlalchemy import select

from app.models.entrada_padron import EntradaPadron
from app.models.version_padron import VersionPadron
from app.repositories.base import BaseRepository


class EntradaPadronRepository(BaseRepository[EntradaPadron]):
    @property
    def model_class(self) -> type[EntradaPadron]:
        return EntradaPadron

    async def list_by_version(self, version_id: UUID) -> Sequence[EntradaPadron]:
        """Return all non-deleted entries for a given version."""
        stmt = select(EntradaPadron).where(
            EntradaPadron.tenant_id == self._tenant_id,
            EntradaPadron.version_id == version_id,
            EntradaPadron.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def list_cohortes_activas_by_usuario(self, usuario_id: UUID) -> list[UUID]:
        """Return distinct cohorte_ids from active padrón versions for this user."""
        stmt = (
            select(VersionPadron.cohorte_id)
            .join(EntradaPadron, EntradaPadron.version_id == VersionPadron.id)
            .where(
                EntradaPadron.tenant_id == self._tenant_id,
                EntradaPadron.usuario_id == usuario_id,
                EntradaPadron.deleted_at.is_(None),
                VersionPadron.activa.is_(True),
                VersionPadron.deleted_at.is_(None),
            )
            .distinct()
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_create(self, entradas: list[EntradaPadron]) -> None:
        """Insert multiple EntradaPadron rows in a single flush."""
        for entrada in entradas:
            entrada.tenant_id = self._tenant_id
            self._session.add(entrada)
        await self._session.flush()
