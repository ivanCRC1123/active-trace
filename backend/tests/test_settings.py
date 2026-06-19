"""Tests for core.config.Settings — pydantic-settings configuration."""

import pytest

from app.core.config import Settings


class TestSettingsValid:
    """Settings loads correctly with valid environment variables."""

    def test_loads_with_valid_env(self):
        """Settings instantiates with minimal valid env vars."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 32,
            "ENCRYPTION_KEY": "b" * 32,
        }
        settings = Settings(_env_file=None, **env)
        assert settings.DATABASE_URL == env["DATABASE_URL"]
        assert settings.SECRET_KEY == env["SECRET_KEY"]
        assert settings.ENCRYPTION_KEY == env["ENCRYPTION_KEY"]

    def test_access_token_expire_defaults_to_15(self):
        """ACCESS_TOKEN_EXPIRE_MINUTES defaults to 15 when not provided."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 32,
            "ENCRYPTION_KEY": "b" * 32,
        }
        settings = Settings(_env_file=None, **env)
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 15


class TestSettingsInvalid:
    """Settings validation rejects invalid configuration."""

    # ── Missing required fields ───────────────────────────────────────
    # These tests must clear the relevant env var because conftest.py
    # sets defaults at module level that pydantic-settings would
    # otherwise pick up via os.environ.

    @pytest.mark.usefixtures("_clear_db_url")
    def test_missing_database_url_raises(self):
        """Missing DATABASE_URL raises ValidationError."""
        env = {
            "SECRET_KEY": "a" * 32,
            "ENCRYPTION_KEY": "b" * 32,
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)

    @pytest.mark.usefixtures("_clear_secret_key")
    def test_missing_secret_key_raises(self):
        """Missing SECRET_KEY raises ValidationError."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "ENCRYPTION_KEY": "b" * 32,
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)

    @pytest.mark.usefixtures("_clear_encryption_key")
    def test_missing_encryption_key_raises(self):
        """Missing ENCRYPTION_KEY raises ValidationError."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 32,
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)

    # ── Invalid values ───────────────────────────────────────────────

    def test_secret_key_too_short_raises(self):
        """SECRET_KEY shorter than 32 chars raises ValidationError."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 31,
            "ENCRYPTION_KEY": "b" * 32,
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)

    def test_encryption_key_wrong_length_raises(self):
        """ENCRYPTION_KEY != 32 chars raises ValidationError."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 32,
            "ENCRYPTION_KEY": "b" * 31,
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)

    def test_invalid_access_token_expire_type_raises(self):
        """Non-integer ACCESS_TOKEN_EXPIRE_MINUTES raises ValidationError."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 32,
            "ENCRYPTION_KEY": "b" * 32,
            "ACCESS_TOKEN_EXPIRE_MINUTES": "not-a-number",
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)

    def test_negative_access_token_expire_raises(self):
        """Negative ACCESS_TOKEN_EXPIRE_MINUTES raises (ge=1)."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 32,
            "ENCRYPTION_KEY": "b" * 32,
            "ACCESS_TOKEN_EXPIRE_MINUTES": -1,
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)

    def test_empty_secret_key_raises(self):
        """Empty SECRET_KEY raises (min_length)."""
        env = {
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
            "SECRET_KEY": "",
            "ENCRYPTION_KEY": "b" * 32,
        }
        with pytest.raises(Exception):
            Settings(_env_file=None, **env)
