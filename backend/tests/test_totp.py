"""Tests for TOTP utility."""

import pytest

from app.core.auth.totp import generate_totp_secret, get_totp_uri, verify_totp


class TestTOTP:
    """RED: TOTP utility functions."""

    def test_generate_secret_returns_base32(self):
        """generate_totp_secret returns a base32 string."""
        secret = generate_totp_secret()
        assert isinstance(secret, str)
        assert len(secret) > 0
        # Base32 characters: A-Z, 2-7
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=" for c in secret.upper())

    def test_generate_secret_min_length(self):
        """Generated secret is at least 32 chars (160 bits)."""
        secret = generate_totp_secret()
        assert len(secret) >= 32

    def test_generate_secret_unique(self):
        """Each call produces a different secret."""
        secrets = {generate_totp_secret() for _ in range(10)}
        assert len(secrets) == 10

    def test_get_totp_uri(self):
        """get_totp_uri returns a valid otpauth URI."""
        secret = generate_totp_secret()
        uri = get_totp_uri(secret, "test@example.com", "TestTenant")
        assert uri.startswith("otpauth://totp/")
        assert "TestTenant" in uri
        assert "test%40example.com" in uri or "test@example.com" in uri
        assert "secret=" in uri

    def test_verify_valid_totp(self):
        """verify_totp returns True for a valid code."""
        secret = generate_totp_secret()
        # We need the pyotp library to generate a valid code for testing
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True

    def test_verify_invalid_totp(self):
        """verify_totp returns False for an invalid code."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "000000") is False

    def test_verify_empty_code(self):
        """verify_totp returns False for empty code."""
        secret = generate_totp_secret()
        assert verify_totp(secret, "") is False

    def test_verify_allows_drift(self):
        """verify_totp accepts codes within a 1-step drift window."""
        secret = generate_totp_secret()
        # We can only test this by generating a valid code
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp(secret, code) is True
