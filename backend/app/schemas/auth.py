"""Pydantic v2 schemas for authentication endpoints.

All schemas use ``model_config = ConfigDict(extra='forbid')``.
"""

import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ── Helpers ──────────────────────────────────────────────────────────────


def _validate_totp_code(v: str) -> str:
    """Validate that a TOTP code is exactly 6 digits."""
    if not re.match(r"^\d{6}$", v):
        raise ValueError("TOTP code must be exactly 6 digits")
    return v


# ── Auth: Login ──────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_code: str
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TwoFARequiredResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires_2fa: bool = True
    session_token: str


# ── Auth: Refresh / Logout ──────────────────────────────────────────────


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class RefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LogoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: Optional[str] = None


class LogoutResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str


# ── 2FA ─────────────────────────────────────────────────────────────────


class TwoFAEnrollResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    secret: str
    uri: str


class TwoFAVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str

    _validate_code = field_validator("code")(_validate_totp_code)


class TwoFAVerifyLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_token: str
    code: str

    _validate_code = field_validator("code")(_validate_totp_code)


# ── Forgot / Reset ──────────────────────────────────────────────────────


class ForgotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ForgotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
    recovery_token: Optional[str] = None


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str
    new_password: str = Field(min_length=8)


class ResetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str


# ── Error ────────────────────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str


# ── CurrentUser (injected via dependency) ────────────────────────────────


class CurrentUser(BaseModel):
    """Represents the authenticated user derived from the JWT.

    This is injected into protected endpoints via ``get_current_user``
    dependency. Never construct from request data — always from JWT.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    tenant_id: UUID
    roles: list[str]
