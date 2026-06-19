"""RefreshToken repository — hash lookup, revoke, family revocation."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.sql import func

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Repository for RefreshToken model."""

    @property
    def model_class(self) -> type[RefreshToken]:
        return RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Find a refresh token by its SHA-256 hash.

        The token hash is globally unique (unique constraint), so no
        tenant filter is needed. The ``tenant_id`` is returned as part
        of the record.

        Args:
            token_hash: The hex-encoded SHA-256 hash.

        Returns:
            The RefreshToken if found, None otherwise.
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

    async def revoke(self, token_id: UUID) -> None:
        """Mark a refresh token as revoked.

        Args:
            token_id: The UUID of the token to revoke (globally unique).
        """
        stmt = (
            update(self.model_class)
            .where(self.model_class.id == token_id)
            .values(revoked_at=func.now())
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def revoke_family(self, family_id: UUID) -> int:
        """Revoke all tokens in a family (across all tenants).

        When token reuse is detected, the entire family is revoked
        regardless of tenant — this is the safest response to a
        suspected token theft.

        Args:
            family_id: The family UUID.

        Returns:
            Number of tokens revoked.
        """
        stmt = (
            update(self.model_class)
            .where(
                self.model_class.family_id == family_id,
                self.model_class.revoked_at.is_(None),
            )
            .values(revoked_at=func.now())
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def find_valid_by_user_id(self, user_id: UUID) -> list[RefreshToken]:
        """Find all valid (non-revoked, non-expired) tokens for a user.

        Args:
            user_id: The user UUID.

        Returns:
            List of valid RefreshToken records.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(self.model_class)
            .where(
                self.model_class.user_id == user_id,
                self.model_class.tenant_id == self._tenant_id,
                self.model_class.revoked_at.is_(None),
                self.model_class.expires_at > now,
                self.model_class.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
