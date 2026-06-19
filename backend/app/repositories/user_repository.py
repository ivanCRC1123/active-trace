"""User repository — tenant-scoped queries with case-insensitive email lookup."""

from uuid import UUID

from sqlalchemy import func, select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User model with email lookup."""

    @property
    def model_class(self) -> type[User]:
        return User

    async def get_by_email(self, email: str) -> User | None:
        """Find a user by email (case-insensitive) within the tenant scope.

        Args:
            email: The email to search for.

        Returns:
            The User if found, None otherwise.
        """
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.tenant_id == self._tenant_id,
                func.lower(self.model_class.email) == func.lower(email),
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
