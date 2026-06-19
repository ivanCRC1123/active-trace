"""RecoveryToken repository — hash lookup and mark_used."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.models.recovery_token import RecoveryToken
from app.repositories.base import BaseRepository


class RecoveryTokenRepository(BaseRepository[RecoveryToken]):
    """Repository for RecoveryToken model."""

    @property
    def model_class(self) -> type[RecoveryToken]:
        return RecoveryToken

    async def get_by_hash(self, token_hash: str) -> RecoveryToken | None:
        """Find a recovery token by its SHA-256 hash.

        Args:
            token_hash: The hex-encoded SHA-256 hash.

        Returns:
            The RecoveryToken if found, None otherwise.
        """
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.token_hash == token_hash,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_used(self, token_id: UUID) -> None:
        """Mark a recovery token as used.

        Args:
            token_id: The UUID of the token to mark as used.
        """
        stmt = (
            update(self.model_class)
            .where(self.model_class.id == token_id)
            .values(used_at=func.now())
        )
        await self._session.execute(stmt)
        await self._session.flush()
