"""Authentication and security primitives.

Provides:
- JWT creation and verification (HS256, python-jose)
- Argon2id password hashing and verification (passlib)
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt as pyjwt
from passlib.hash import argon2

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Argon2id ──────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using Argon2id.

    Uses the Argon2id variant via passlib's argon2 wrapper.

    Args:
        password: The plaintext password to hash.

    Returns:
        A PHC-formatted hash string (contains salt, params, and digest).
    """
    logger.debug("Hashing password with Argon2id.")
    return argon2.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its Argon2id hash.

    Args:
        password: The plaintext password to verify.
        password_hash: The PHC-format Argon2id hash string.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    try:
        return argon2.verify(password, password_hash)
    except Exception:  # noqa: BLE001
        logger.warning("Password verification failed (possible hash format issue).")
        return False


# ── JWT ───────────────────────────────────────────────────────────────────


def create_access_token(
    user_id: UUID,
    tenant_id: UUID,
    roles: list[str],
) -> str:
    """Create a signed JWT access token.

    Claims:
    - ``sub``: user UUID (as string)
    - ``tenant_id``: tenant UUID (as string)
    - ``roles``: list of role strings
    - ``exp``: expiration timestamp (UTC, configurable minutes from now)

    Args:
        user_id: The user's UUID.
        tenant_id: The tenant's UUID.
        roles: List of role names for the user.

    Returns:
        A signed JWT string (HS256 algorithm).
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "roles": roles,
        "exp": expire,
    }

    token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    logger.debug("JWT access token created.")
    return token


def verify_access_token(token: str) -> dict:
    """Verify and decode a JWT access token.

    Args:
        token: The JWT string to verify.

    Returns:
        The decoded payload dictionary.

    Raises:
        jwt.ExpiredSignatureError: If the token has expired.
        jwt.InvalidSignatureError: If the signature is invalid.
        ValueError: If the token is missing required claims (e.g. ``sub``).
        jwt.PyJWTError: For any other JWT-related errors.
    """
    payload = pyjwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=["HS256"],
    )

    if "sub" not in payload:
        raise ValueError("JWT payload is missing 'sub' claim")

    logger.debug("JWT access token verified.")
    return payload
