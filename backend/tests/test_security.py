"""Tests for core/security.py — JWT + Argon2id utilities.

Strict TDD: RED → GREEN → TRIANGULATE.
"""

import time
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    hash_password,
    verify_access_token,
    verify_password,
)


# ── Argon2id: hash_password ────────────────────────────────────────────


class TestHashPassword:
    """RED: hash_password produces different hash each call."""

    def test_hash_password_returns_string(self):
        """Hash is a non-empty string."""
        h = hash_password("securePass123!")
        assert isinstance(h, str)
        assert len(h) > 0

    def test_hash_password_differs_each_call(self):
        """Same password produces different hashes (salt)."""
        h1 = hash_password("securePass123!")
        h2 = hash_password("securePass123!")
        assert h1 != h2


# ── Argon2id: verify_password ──────────────────────────────────────────


class TestVerifyPassword:
    """RED: verify_password returns True/False correctly."""

    def test_verify_password_correct(self):
        """verify_password returns True for matching password."""
        h = hash_password("correct-horse-battery")
        assert verify_password("correct-horse-battery", h) is True

    def test_verify_password_wrong(self):
        """verify_password returns False for wrong password."""
        h = hash_password("the-right-one")
        assert verify_password("the-wrong-one", h) is False

    def test_verify_password_empty(self):
        """Empty password does not match a hashed password."""
        h = hash_password("something")
        assert verify_password("", h) is False


# ── JWT: create_access_token ────────────────────────────────────────────


class TestCreateAccessToken:
    """RED: create_access_token returns a valid JWT string."""

    def test_returns_string(self):
        """create_access_token returns a non-empty string."""
        token = create_access_token(
            user_id=uuid4(),
            tenant_id=uuid4(),
            roles=["admin"],
        )
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_is_jwt_with_three_parts(self):
        """JWT string has 3 dot-separated segments."""
        token = create_access_token(uuid4(), uuid4(), ["admin"])
        parts = token.split(".")
        assert len(parts) == 3

    def test_token_contains_correct_claims(self):
        """Token payload contains sub, tenant_id, roles, exp."""
        uid = uuid4()
        tid = uuid4()
        token = create_access_token(uid, tid, ["admin", "coordinator"])
        payload = verify_access_token(token)
        assert payload["sub"] == str(uid)
        assert payload["tenant_id"] == str(tid)
        assert payload["roles"] == ["admin", "coordinator"]
        assert "exp" in payload

    def test_token_expiry(self):
        """Token expires at expected time (configurable)."""
        token = create_access_token(uuid4(), uuid4(), ["user"])
        payload = verify_access_token(token)
        now = time.time()
        # Default is 15 min = 900 seconds
        expected_exp = int(now) + 900
        # Allow some tolerance for test execution
        assert abs(payload["exp"] - expected_exp) < 10


# ── JWT: verify_access_token ────────────────────────────────────────────


class TestVerifyAccessToken:
    """RED: verify_access_token raises on expired / invalid tokens."""

    def test_verify_valid_token(self):
        """Valid token returns correct payload."""
        uid = uuid4()
        tid = uuid4()
        token = create_access_token(uid, tid, ["profesor"])
        payload = verify_access_token(token)
        assert payload["sub"] == str(uid)

    def test_expired_token_raises(self):
        """Expired token raises jwt.ExpiredSignatureError."""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "roles": [],
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        with pytest.raises(jwt.ExpiredSignatureError):
            verify_access_token(token)

    def test_invalid_signature_raises(self):
        """Token with wrong signature raises jwt.InvalidSignatureError."""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "roles": [],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        # Sign with a different key
        token = pyjwt.encode(payload, "some-other-secret-key-1234567890!", algorithm="HS256")
        with pytest.raises(jwt.InvalidSignatureError):
            verify_access_token(token)


# ── TRIANGULATE ─────────────────────────────────────────────────────────


class TestTriangulate:
    """Additional edge cases (task 2.3)."""

    def test_missing_sub_claim_raises_value_error(self):
        """Token without 'sub' claim raises ValueError."""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "tenant_id": str(uuid4()),
            "roles": [],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
        with pytest.raises(ValueError, match="missing 'sub' claim"):
            verify_access_token(token)

    def test_tampered_token_raises_jwt_error(self):
        """Tampered token raises jwt.PyJWTError."""
        token = create_access_token(uuid4(), uuid4(), [])
        # Tamper with the signature part
        parts = token.split(".")
        tampered = f"{parts[0]}.{parts[1]}.invalidsignature"
        with pytest.raises(jwt.PyJWTError):
            verify_access_token(tampered)

    def test_configurable_expiry(self):
        """create_access_token uses expiry from settings."""
        from app.core.config import settings as s

        uid = uuid4()
        tid = uuid4()
        token = create_access_token(uid, tid, ["test"])
        payload = verify_access_token(token)
        # Default is 15 min = 900 seconds
        assert payload["exp"] - int(time.time()) <= s.ACCESS_TOKEN_EXPIRE_MINUTES * 60 + 5
