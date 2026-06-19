"""Rol repository — tenant-scoped CRUD with name lookup."""

from sqlalchemy import select

from app.models.rol import Rol
from app.repositories.base import BaseRepository


class RolRepository(BaseRepository[Rol]):
    """Repository for Rol model with name lookup."""

    @property
    def model_class(self) -> type[Rol]:
        return Rol

    async def find_by_nombre(self, nombre: str) -> Rol | None:
        """Find a role by name within the tenant scope.

        Args:
            nombre: The role name to search for (e.g., "ADMIN").

        Returns:
            The Rol if found, None otherwise.
        """
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.tenant_id == self._tenant_id,
                self.model_class.nombre == nombre,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
