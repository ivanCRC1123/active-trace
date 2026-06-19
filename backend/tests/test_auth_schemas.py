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
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
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


class TestRefreshRequest:
    """RED: RefreshRequest accepts refresh_token."""

    def test_valid(self):
        req = RefreshRequest(refresh_token="abc123")
        assert req.refresh_token == "abc123"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            RefreshRequest(refresh_token="abc", extra="bad")


class TestTokenResponse:
    """RED: TokenResponse contains access_token, refresh_token, token_type, expires_in."""

    def test_valid(self):
        resp = LoginResponse(
            access_token="at", refresh_token="rt",
            token_type="bearer", expires_in=900,
        )
        assert resp.access_token == "at"
        assert resp.refresh_token == "rt"
        assert resp.token_type == "bearer"
        assert resp.expires_in == 900

    def test_default_token_type(self):
        resp = LoginResponse(access_token="at", refresh_token="rt", expires_in=900)
        assert resp.token_type == "bearer"

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            LoginResponse(access_token="a", refresh_token="b", expires_in=1, extra="x")


class TestRefreshResponse:
    """RED: RefreshResponse same shape as LoginResponse."""

    def test_valid(self):
        resp = RefreshResponse(access_token="at", refresh_token="rt", expires_in=900)
        assert resp.access_token
        assert resp.refresh_token
        assert resp.token_type == "bearer"


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


class TestLogoutRequest:
    """RED: LogoutRequest accepts optional refresh_token."""

    def test_valid_with_token(self):
        req = LogoutRequest(refresh_token="rt123")
        assert req.refresh_token == "rt123"

    def test_valid_without_token(self):
        req = LogoutRequest()
        assert req.refresh_token is None


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
