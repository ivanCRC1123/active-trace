"""AuthService — orchestrates authentication flows.

All auth business logic lives here, not in routers.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.rate_limiter import InMemoryRateLimiter
from app.core.auth.totp import generate_totp_secret, get_totp_uri, verify_totp
from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.recovery_token_repository import RecoveryTokenRepository
from app.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Convert a datetime to naive UTC, stripping timezone info.

    Works around asyncpg / PyMongo timezone-awareness mismatches on Windows.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _utcnow_naive() -> datetime:
    """Return the current UTC time as a naive datetime.

    Replacement for deprecated ``datetime.utcnow()``.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthService:
    """Handles login, 2FA, refresh, logout, password recovery.

    Uses tenant-scoped repositories and session-based tenant resolution.
    """

    def __init__(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        user_repo: UserRepository,
        refresh_repo: RefreshTokenRepository,
        recovery_repo: RecoveryTokenRepository,
        max_attempts: int | None = None,
    ):
        self._session = session
        self._tenant_id = tenant_id
        self._user_repo = user_repo
        self._refresh_repo = refresh_repo
        self._recovery_repo = recovery_repo
        self._rate_limiter = InMemoryRateLimiter(
            max_attempts=max_attempts or settings.RATE_LIMIT_MAX_ATTEMPTS,
        )

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _hash_token(token: str) -> str:
        """SHA-256 hex digest of a token."""
        return hashlib.sha256(token.encode()).hexdigest()

    def _generate_refresh_token_value(self) -> str:
        """Cryptographically random token string."""
        return secrets.token_urlsafe(48)

    async def _get_user_role_names(self, user_id: UUID, tenant_id: UUID) -> list[str]:
        """Query UserRol + Rol for active role names.

        Args:
            user_id: The user's UUID.
            tenant_id: The tenant's UUID.

        Returns:
            A list of role name strings (e.g., ``["ADMIN", "PROFESOR"]``).
            Empty list if the user has no role assignments.
        """
        from app.models.rol import Rol  # noqa: PLC0415
        from app.models.user_rol import UserRol  # noqa: PLC0415

        stmt = (
            select(Rol.nombre)
            .join(UserRol, UserRol.rol_id == Rol.id)
            .where(
                UserRol.user_id == user_id,
                UserRol.tenant_id == tenant_id,
                UserRol.deleted_at.is_(None),
                Rol.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]

    async def _issue_tokens(self, user: User) -> dict:
        """Create and persist access+refresh tokens, return them."""
        roles = await self._get_user_role_names(user.id, user.tenant_id)
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            roles=roles,
        )
        refresh_value = self._generate_refresh_token_value()
        refresh_hash = self._hash_token(refresh_value)
        family_id = uuid4()
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        )

        # Create refresh token directly with user's tenant_id.
        # We bypass the repo's create() which would override with
        # the service's tenant_id — the user's tenant is always correct.
        from app.models.refresh_token import RefreshToken
        token = RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            family_id=family_id,
            expires_at=expires_at,
            tenant_id=user.tenant_id,
        )
        self._session.add(token)
        await self._session.flush()

        return {
            "access_token": access_token,
            "refresh_token": refresh_value,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def _resolve_tenant(self, tenant_code: str) -> UUID | None:
        """Resolve tenant code to tenant UUID."""
        stmt = select(Tenant).where(
            Tenant.codigo == tenant_code,
            Tenant.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        tenant = result.scalar_one_or_none()
        return tenant.id if tenant else None

    # ── Session token for 2FA ─────────────────────────────────────────

    _pending_2fa: dict[str, dict] = {}  # session_token → {user_id, tenant_id}

    async def _create_2fa_session(self, user: User) -> str:
        """Create a temporary session token for 2FA verification."""
        session_token = secrets.token_urlsafe(32)
        self._pending_2fa[session_token] = {
            "user_id": str(user.id),
            "tenant_id": str(user.tenant_id),
            "created_at": _utcnow_naive(),
        }
        return session_token

    async def _resolve_2fa_session(self, session_token: str) -> dict | None:
        """Resolve a 2FA session token, return stored data or None."""
        data = self._pending_2fa.get(session_token)
        if data is None:
            return None
        # Clean up — one-time use
        del self._pending_2fa[session_token]
        # Check expiry (5 minutes)
        created = data["created_at"]
        if _utcnow_naive() - created > timedelta(minutes=5):
            return None
        return data

    # ── Public API ────────────────────────────────────────────────────

    async def login(
        self,
        tenant_code: str,
        email: str,
        password: str,
        ip_address: str = "",
    ) -> dict:
        """Authenticate a user and return tokens or 2FA challenge.

        Returns:
            Dict with ``access_token``, ``refresh_token``,
            ``expires_in``, ``token_type`` on success.
            If 2FA is required, returns ``requires_2fa`` and
            ``session_token``.
        """
        rate_limit_key = f"{ip_address}:{tenant_code}:{email.lower()}"
        if not await self._rate_limiter.check(rate_limit_key):
            raise ValueError("Too many login attempts. Please try again later.")

        # Resolve tenant code to ID
        tenant_id = await self._resolve_tenant(tenant_code)
        if tenant_id is None:
            raise ValueError("Invalid email or password")

        # Set tenant on repo (in case it differs from service tenant)
        user_repo = UserRepository(self._session, tenant_id)
        user = await user_repo.get_by_email_hash(email)
        if user is None:
            raise ValueError("Invalid email or password")

        if not user.is_active:
            raise ValueError("Account is inactive")

        if not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password")

        # Check 2FA
        if user.is_2fa_enabled:
            session_token = await self._create_2fa_session(user)
            return {
                "requires_2fa": True,
                "session_token": session_token,
            }

        return await self._issue_tokens(user)

    async def verify_2fa_login(self, session_token: str, code: str) -> dict:
        """Complete 2FA challenge and issue tokens."""
        data = await self._resolve_2fa_session(session_token)
        if data is None:
            raise ValueError("Invalid or expired session token")

        user_id = UUID(data["user_id"])
        tenant_id = UUID(data["tenant_id"])

        user_repo = UserRepository(self._session, tenant_id)
        user = await user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        if not user.totp_secret or not verify_totp(user.totp_secret, code):
            raise ValueError("Invalid TOTP code")

        return await self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> dict:
        """Rotate a refresh token and issue new tokens.

        Implements token rotation with family revocation:
        - If the token has been revoked → revoke entire family (reuse detected).
        """
        token_hash = self._hash_token(refresh_token)
        stored = await self._refresh_repo.get_by_hash(token_hash)

        if stored is None:
            raise ValueError("Refresh token not found")

        if stored.revoked_at is not None:
            # Token reuse detected — revoke entire family
            await self._refresh_repo.revoke_family(stored.family_id)
            raise ValueError("Refresh token has been revoked")

        if _naive_utc(stored.expires_at) < _utcnow_naive():
            raise ValueError("Refresh token has expired")

        # Revoke the old token
        await self._refresh_repo.revoke(stored.id)

        # Get user — use tenant from stored token, not service constructor
        user_repo = UserRepository(self._session, stored.tenant_id)
        user = await user_repo.get_by_id(stored.user_id)
        if user is None:
            raise ValueError("User not found")

        # Issue new tokens
        roles = await self._get_user_role_names(user.id, user.tenant_id)
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            roles=roles,
        )
        new_refresh_value = self._generate_refresh_token_value()
        new_refresh_hash = self._hash_token(new_refresh_value)
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        )

        # Create directly with user's tenant_id (same pattern as _issue_tokens)
        from app.models.refresh_token import RefreshToken as RT
        new_token = RT(
            user_id=user.id,
            token_hash=new_refresh_hash,
            family_id=stored.family_id,
            expires_at=expires_at,
            tenant_id=user.tenant_id,
        )
        self._session.add(new_token)
        await self._session.flush()

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_value,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    async def logout(self, refresh_token: str | None) -> None:
        """Revoke a refresh token, if provided."""
        if refresh_token is None:
            return
        token_hash = self._hash_token(refresh_token)
        stored = await self._refresh_repo.get_by_hash(token_hash)
        if stored is not None and stored.revoked_at is None:
            await self._refresh_repo.revoke(stored.id)

    async def forgot_password(
        self,
        tenant_code: str,
        email: str,
    ) -> str | None:
        """Generate a password recovery token.

        Returns the raw token string (to be sent via email), or None
        if the email is unknown (don't leak user existence).
        """
        tenant_id = await self._resolve_tenant(tenant_code)
        if tenant_id is None:
            return None

        user_repo = UserRepository(self._session, tenant_id)
        user = await user_repo.get_by_email_hash(email)
        if user is None:
            return None

        # Generate recovery token
        raw_token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        await self._recovery_repo.create({
            "user_id": user.id,
            "token_hash": token_hash,
            "expires_at": expires_at,
        })

        return raw_token

    async def reset_password(self, token: str, new_password: str) -> None:
        """Reset password using a recovery token."""
        token_hash = self._hash_token(token)
        stored = await self._recovery_repo.get_by_hash(token_hash)

        if stored is None or stored.used_at is not None:
            raise ValueError("Invalid or expired recovery token")

        if _naive_utc(stored.expires_at) < _utcnow_naive():
            raise ValueError("Invalid or expired recovery token")

        # Mark as used
        await self._recovery_repo.mark_used(stored.id)

        # Update password
        stmt = (
            User.__table__.update()
            .where(User.id == stored.user_id)
            .values(password_hash=hash_password(new_password))
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def change_password(
        self,
        user_id: UUID,
        old_password: str,
        new_password: str,
    ) -> None:
        """Change password for an authenticated user."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        if not verify_password(old_password, user.password_hash):
            raise ValueError("Current password is incorrect")

        stmt = (
            User.__table__.update()
            .where(User.id == user_id)
            .values(password_hash=hash_password(new_password))
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def enroll_2fa(self, user_id: UUID) -> dict:
        """Generate a TOTP secret and provisioning URI for a user.

        Does NOT enable 2FA yet — call ``enable_2fa`` with a verified code.
        """
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        secret = generate_totp_secret()
        uri = get_totp_uri(secret, user.email_cifrado, issuer="Trace")

        # Store the secret (but don't enable 2FA yet)
        stmt = (
            User.__table__.update()
            .where(User.id == user_id)
            .values(totp_secret=secret)
        )
        await self._session.execute(stmt)
        await self._session.flush()

        return {"secret": secret, "uri": uri}

    async def enable_2fa(self, user_id: UUID, code: str) -> None:
        """Verify a TOTP code and enable 2FA for the user."""
        user = await self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")

        if not user.totp_secret:
            raise ValueError("TOTP not enrolled. Call enroll_2fa first.")

        if not verify_totp(user.totp_secret, code):
            raise ValueError("Invalid TOTP code")

        stmt = (
            User.__table__.update()
            .where(User.id == user_id)
            .values(is_2fa_enabled=True)
        )
        await self._session.execute(stmt)
        await self._session.flush()
