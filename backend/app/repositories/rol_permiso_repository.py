"""RolPermiso repository — role-permission matrix queries."""

from sqlalchemy import select

from app.models.permiso import Permiso
from app.models.rol import Rol
from app.models.rol_permiso import RolPermiso
from app.models.user_rol import UserRol
from app.repositories.base import BaseRepository


class RolPermisoRepository(BaseRepository[RolPermiso]):
    """Repository for RolPermiso matrix with role-based lookups."""

    @property
    def model_class(self) -> type[RolPermiso]:
        return RolPermiso

    async def get_permissions_for_roles(
        self, rol_ids: list[str],
    ) -> list[tuple[str, str]]:
        """Get all (permiso_codigo, scope) pairs for a set of roles.

        Args:
            rol_ids: List of role UUIDs to query.

        Returns:
            List of (codigo, scope) tuples.
        """
        if not rol_ids:
            return []

        stmt = (
            select(Permiso.codigo, RolPermiso.scope)
            .join(RolPermiso, RolPermiso.permiso_id == Permiso.id)
            .where(
                RolPermiso.rol_id.in_(rol_ids),
                RolPermiso.tenant_id == self._tenant_id,
                RolPermiso.deleted_at.is_(None),
                Permiso.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_roles_for_permission(
        self, permiso_id: str,
    ) -> list[Rol]:
        """Get all roles that have a specific permission.

        Args:
            permiso_id: The permission UUID.

        Returns:
            List of Rol objects.
        """
        stmt = (
            select(Rol)
            .join(RolPermiso, RolPermiso.rol_id == Rol.id)
            .where(
                RolPermiso.permiso_id == permiso_id,
                RolPermiso.tenant_id == self._tenant_id,
                RolPermiso.deleted_at.is_(None),
                Rol.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
