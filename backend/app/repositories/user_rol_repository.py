"""UserRol repository — user-role assignment queries."""

from sqlalchemy import select

from app.models.rol import Rol
from app.models.user import User
from app.models.user_rol import UserRol
from app.repositories.base import BaseRepository


class UserRolRepository(BaseRepository[UserRol]):
    """Repository for UserRol with user and role lookups."""

    @property
    def model_class(self) -> type[UserRol]:
        return UserRol

    async def get_roles_for_user(self, user_id: str) -> list[Rol]:
        """Get all active roles assigned to a user.

        Args:
            user_id: The user UUID.

        Returns:
            List of Rol objects assigned to the user.
        """
        stmt = (
            select(Rol)
            .join(UserRol, UserRol.rol_id == Rol.id)
            .where(
                UserRol.user_id == user_id,
                UserRol.tenant_id == self._tenant_id,
                UserRol.deleted_at.is_(None),
                Rol.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_users_for_role(self, rol_id: str) -> list[User]:
        """Get all users assigned to a specific role.

        Args:
            rol_id: The role UUID.

        Returns:
            List of User objects with that role.
        """
        stmt = (
            select(User)
            .join(UserRol, UserRol.user_id == User.id)
            .where(
                UserRol.rol_id == rol_id,
                UserRol.tenant_id == self._tenant_id,
                UserRol.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
