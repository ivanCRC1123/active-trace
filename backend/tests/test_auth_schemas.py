"""Tests for auth Pydantic schemas — validation, extra='forbid'."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    CurrentUser,
    ErrorResponse,
    ForgotRequest,
    ForgotResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MePermissionsResponse,
    RefreshResponse,
    ResetRequest,
    TwoFAEnrollResponse,
    TwoFARequiredResponse,
    TwoFAVerifyLoginRequest,
    TwoFAVerifyRequest,
)


class TestLoginRequest:
    """RED: LoginRequest accepts tenant_code + email + password."""

    def test_valid(self):
        req = LoginRequest(tenant_code="tupad", email="a@b.com", password="secret")
        assert req.tenant_code == "tupad"
        assert req.email == "a@b.com"
        assert req.password == "secret"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            LoginRequest(tenant_code="tupad", email="a@b.com", password="s", extra="bad")

    def test_missing_tenant_code_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com", password="s")

    def test_missing_email_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(tenant_code="tupad", password="s")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(tenant_code="tupad", email="a@b.com")


class TestTokenResponse:
    """LoginResponse contains access_token, token_type, expires_in.

    The refresh token is no longer in the JSON body — it is set as an
    httpOnly cookie by the endpoint (Opción D, design.md D1).
    """

    def test_valid(self):
        resp = LoginResponse(access_token="at", token_type="bearer", expires_in=900)
        assert resp.access_token == "at"
        assert resp.token_type == "bearer"
        assert resp.expires_in == 900

    def test_default_token_type(self):
        resp = LoginResponse(access_token="at", expires_in=900)
        assert resp.token_type == "bearer"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            LoginResponse(access_token="a", expires_in=1, extra="x")

    def test_no_refresh_token_field(self):
        """refresh_token is not part of LoginResponse (cookie-based)."""
        with pytest.raises(ValidationError):
            LoginResponse(access_token="a", refresh_token="r", expires_in=1)


class TestRefreshResponse:
    """RefreshResponse: access_token only — no refresh_token in body."""

    def test_valid(self):
        resp = RefreshResponse(access_token="at", expires_in=900)
        assert resp.access_token == "at"
        assert resp.token_type == "bearer"

    def test_no_refresh_token_field(self):
        with pytest.raises(ValidationError):
            RefreshResponse(access_token="at", refresh_token="rt", expires_in=900)


class TestMePermissionsResponse:
    """MePermissionsResponse wraps the effective permission map."""

    def test_valid_empty(self):
        resp = MePermissionsResponse(permissions={})
        assert resp.permissions == {}

    def test_valid_with_permissions(self):
        resp = MePermissionsResponse(permissions={"calificaciones:importar": "own"})
        assert resp.permissions["calificaciones:importar"] == "own"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            MePermissionsResponse(permissions={}, extra="x")


class TestForgotRequest:
    """RED: ForgotRequest accepts email."""

    def test_valid(self):
        req = ForgotRequest(email="user@test.com")
        assert req.email == "user@test.com"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ForgotRequest(email="a@b.com", extra="x")


class TestForgotResponse:
    """RED: ForgotResponse has detail + optional recovery_token."""

    def test_with_token(self):
        resp = ForgotResponse(detail="ok", recovery_token="tok123")
        assert resp.recovery_token == "tok123"

    def test_without_token(self):
        resp = ForgotResponse(detail="ok")
        assert resp.recovery_token is None


class TestResetRequest:
    """RED: ResetRequest accepts token + new_password."""

    def test_valid(self):
        req = ResetRequest(token="tok123", new_password="newPass123!")
        assert req.token == "tok123"
        assert req.new_password == "newPass123!"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ResetRequest(token="a", new_password="12345678", extra="x")

    def test_rejects_short_password(self):
        with pytest.raises(ValidationError, match="at least 8 characters"):
            ResetRequest(token="a", new_password="1234567")


class TestTwoFAEnrollResponse:
    """RED: TwoFAEnrollResponse contains secret + uri."""

    def test_valid(self):
        resp = TwoFAEnrollResponse(secret="JBSWY3DPEHPK3PXP", uri="otpauth://totp/...")
        assert resp.secret
        assert resp.uri


class TestTwoFAVerifyRequest:
    """RED: TwoFAVerifyRequest accepts code with 6-digit validation."""

    def test_valid(self):
        req = TwoFAVerifyRequest(code="123456")
        assert req.code == "123456"

    def test_rejects_non_digit(self):
        with pytest.raises(ValidationError):
            TwoFAVerifyRequest(code="abcd12")

    def test_rejects_short_code(self):
        with pytest.raises(ValidationError):
            TwoFAVerifyRequest(code="12345")

    def test_rejects_long_code(self):
        with pytest.raises(ValidationError):
            TwoFAVerifyRequest(code="1234567")


class TestTwoFAVerifyLoginRequest:
    """RED: TwoFAVerifyLoginRequest accepts session_token + code."""

    def test_valid(self):
        req = TwoFAVerifyLoginRequest(session_token="st123", code="654321")
        assert req.session_token == "st123"
        assert req.code == "654321"


class TestTwoFARequiredResponse:
    """RED: TwoFARequiredResponse has requires_2fa + session_token."""

    def test_valid(self):
        resp = TwoFARequiredResponse(session_token="st123")
        assert resp.requires_2fa is True
        assert resp.session_token == "st123"


class TestLogoutResponse:
    def test_valid(self):
        resp = LogoutResponse(detail="Logged out")
        assert resp.detail == "Logged out"


class TestErrorResponse:
    def test_valid(self):
        resp = ErrorResponse(detail="Something went wrong")
        assert resp.detail == "Something went wrong"


class TestCurrentUser:
    """RED: CurrentUser schema."""

    def test_valid(self):
        cu = CurrentUser(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=["admin"])
        assert cu.roles == ["admin"]

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            CurrentUser(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), roles=[], extra="x")


# ── TRIANGULATE ─────────────────────────────────────────────────────────


class TestTriangulate:
    def test_login_email_validation(self):
        """LoginRequest validates email format."""
        from pydantic import EmailStr
        # EmailStr is used; test that invalid email is rejected
        with pytest.raises(ValidationError):
            LoginRequest(tenant_code="t", email="not-an-email", password="p")

    def test_reset_rejects_short_password(self):
        with pytest.raises(ValidationError, match="at least 8 characters"):
            ResetRequest(token="a", new_password="short")
