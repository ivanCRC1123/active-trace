"""User repository — tenant-scoped queries with blind-index email lookup."""

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User model. Email lookup via HMAC-SHA256 blind index."""

    @property
    def model_class(self) -> type[User]:
        return User

    async def get_by_email_hash(self, email: str) -> User | None:
        """Find a user by email within the tenant scope using the blind index.

        Args:
            email: The plaintext email to search for (normalized internally).

        Returns:
            The User if found, None otherwise.
        """
        from app.core.encryption import hmac_email  # noqa: PLC0415
        h = hmac_email(email)
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.tenant_id == self._tenant_id,
                self.model_class.email_hash == h,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
