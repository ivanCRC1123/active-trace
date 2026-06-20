"""FastAPI dependencies.

- ``get_db`` — request-scoped async session (C-01)
- ``get_current_user`` — resolves identity + tenant from verified JWT (C-03)
- ``get_moodle_client`` — Moodle WS client (C-09)

Permission guard dependencies live in ``app.core.permissions``:
- ``require_permission`` — RBAC guard that checks a specific permission (C-04)
"""

import logging
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidSignatureError, PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.security import verify_access_token
from app.integrations.moodle_ws import MoodleWSClient, MoodleWSClientProtocol
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import CurrentUser

logger = logging.getLogger(__name__)

# Reusable Bearer token extractor (auto-returns 401 if missing/malformed)
bearer_scheme = HTTPBearer(auto_error=True)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async database session.

    The session is created from ``async_session_factory``, yielded to
    the caller, and **always** closed in the ``finally`` block —
    even if the caller raises an exception. This guarantees that no
    connection leaks back to the pool.
    """
    if async_session_factory is None:
        raise RuntimeError(
            "Database not initialised. Call init_engine() first."
        )
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Extract, verify JWT and return the current authenticated user.

    The identity and tenant are derived **exclusively** from the JWT.
    No request parameter can modify them (Rule D9).

    Raises:
        HTTPException 401: If the token is missing, expired,
            invalidly-signed, or the user is deactivated.
    """
    token = credentials.credentials
    try:
        payload = verify_access_token(token)
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except (InvalidSignatureError, PyJWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user_id = UUID(payload["sub"])
    tenant_id = UUID(payload["tenant_id"])
    roles: list[str] = payload.get("roles", [])

    impersonado_id_str = payload.get("impersonado_id")
    impersonado_id = UUID(impersonado_id_str) if impersonado_id_str else None

    # Verify user is still active in DB
    user_repo = UserRepository(db, tenant_id)
    user = await user_repo.get_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return CurrentUser(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        impersonado_id=impersonado_id,
    )


def get_moodle_client() -> MoodleWSClientProtocol:
    """Return the configured Moodle WS client.

    Returns an unconfigured client when MOODLE_BASE_URL is empty;
    the service layer raises 503 in that case.
    """
    from app.core.config import settings  # noqa: PLC0415

    return MoodleWSClient(
        base_url=settings.MOODLE_BASE_URL,
        token=settings.MOODLE_WS_TOKEN,
    )
