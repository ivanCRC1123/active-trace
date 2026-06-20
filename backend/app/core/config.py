"""Application configuration via pydantic-settings.

Defines the Settings class that loads and validates all environment
variables required by the application. Validation occurs at startup:
invalid or missing values prevent the app from booting.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration loaded from environment / .env file.

    All variables are validated at instantiation time. Missing required
    variables or values that fail validation raise a ``ValidationError``
    that prevents the application from starting.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # ── Required ──────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        description="PostgreSQL connection string (asyncpg driver)",
    )

    SECRET_KEY: str = Field(
        min_length=32,
        description="JWT signing key — minimum 32 characters",
    )

    ENCRYPTION_KEY: str = Field(
        min_length=32,
        max_length=32,
        description="AES-256 key for PII/secretos — exactly 32 characters",
    )

    # ── Optional (with defaults) ──────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=15,
        ge=1,
        description="Access token lifetime in minutes",
    )

    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(
        default=7,
        ge=1,
        description="Refresh token lifetime in days",
    )

    SEED_ADMIN_EMAIL: str = Field(
        default="admin@tupad.edu.ar",
        description="Email for the initial admin seed user",
    )

    SEED_ADMIN_PASSWORD: str = Field(
        default="admin1234",
        min_length=8,
        description="Password for the initial admin seed user",
    )

    RATE_LIMIT_MAX_ATTEMPTS: int = Field(
        default=5,
        ge=1,
        description="Maximum login attempts per sliding window",
    )

    RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        ge=1,
        description="Sliding window size in seconds for rate limiting",
    )

    # ── Moodle Web Services (optional) ───────────────────────────────
    MOODLE_BASE_URL: str = Field(
        default="",
        description="Base URL del Moodle del tenant (vacío = integración deshabilitada)",
    )

    MOODLE_WS_TOKEN: str = Field(
        default="",
        description="Token de acceso al Moodle Web Services REST API",
    )

    # ── Optional test database ────────────────────────────────────────
    DATABASE_URL_TEST: str | None = Field(
        default=None,
        description="PostgreSQL connection string for tests (optional)",
    )

    # ── Validators ────────────────────────────────────────────────────

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long"
            )
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validate_encryption_key_length(cls, v: str) -> str:
        if len(v) != 32:
            raise ValueError(
                "ENCRYPTION_KEY must be exactly 32 characters long"
            )
        return v


# Module-level singleton (loaded once at import / app startup).
settings = Settings()
