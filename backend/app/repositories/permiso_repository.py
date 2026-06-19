"""Permiso repository — tenant-scoped CRUD with code and module lookups."""

from sqlalchemy import select

from app.models.permiso import Permiso
from app.repositories.base import BaseRepository


class PermisoRepository(BaseRepository[Permiso]):
    """Repository for Permiso model with code and module lookups."""

    @property
    def model_class(self) -> type[Permiso]:
        return Permiso

    async def find_by_codigo(self, codigo: str) -> Permiso | None:
        """Find a permission by code within the tenant scope.

        Args:
            codigo: The permission code (e.g., ``"calificaciones:importar"``).

        Returns:
            The Permiso if found, None otherwise.
        """
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.tenant_id == self._tenant_id,
                self.model_class.codigo == codigo,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_modulo(self, modulo: str) -> list[Permiso]:
        """Find all permissions for a given module.

        Args:
            modulo: The module name (e.g., ``"calificaciones"``).

        Returns:
            List of Permiso objects for that module.
        """
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.tenant_id == self._tenant_id,
                self.model_class.modulo == modulo,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
