"""Tests for AuthService."""

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.service import AuthService
from app.core.auth.totp import generate_totp_secret, verify_totp
from app.core.config import settings
from app.core.security import hash_password
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.recovery_token_repository import RecoveryTokenRepository
from app.repositories.user_repository import UserRepository

# ── DDL ───────────────────────────────────────────────────────────────

TENANT_DDL = text("""
    CREATE TABLE IF NOT EXISTS tenant (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        codigo          VARCHAR(50) NOT NULL UNIQUE,
        nombre          VARCHAR(255) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
""")

USER_DDL = text("""
    CREATE TABLE IF NOT EXISTS "user" (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email_cifrado       TEXT NOT NULL,
        email_hash          VARCHAR(64) NOT NULL,
        password_hash       VARCHAR(255) NOT NULL,
        nombre              VARCHAR(100) NOT NULL,
        apellidos           VARCHAR(255) NOT NULL,
        is_2fa_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
        totp_secret         TEXT,
        is_active           BOOLEAN NOT NULL DEFAULT TRUE,
        tenant_id           UUID NOT NULL REFERENCES tenant(id),
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at          TIMESTAMPTZ
    )
""")

REFRESH_DDL = text("""
    CREATE TABLE IF NOT EXISTS refresh_token (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id         UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
        token_hash      VARCHAR(64) NOT NULL UNIQUE,
        family_id       UUID NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        revoked_at      TIMESTAMPTZ,
        tenant_id       UUID NOT NULL REFERENCES tenant(id),
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
""")

RECOVERY_DDL = text("""
    CREATE TABLE IF NOT EXISTS recovery_token (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id         UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
        tenant_id       UUID NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
        token_hash      VARCHAR(64) NOT NULL UNIQUE,
        expires_at      TIMESTAMPTZ NOT NULL,
        used_at         TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
""")


async def _ensure_tables(session: AsyncSession):
    """Create tables, clean data."""
    await session.execute(TENANT_DDL)
    await session.execute(USER_DDL)
    await session.execute(REFRESH_DDL)
    await session.execute(RECOVERY_DDL)
    await session.execute(text("DELETE FROM asignacion"))
    await session.execute(text("DELETE FROM recovery_token"))
    await session.execute(text("DELETE FROM refresh_token"))
    await session.execute(text('DELETE FROM "user"'))
    await session.execute(text("DELETE FROM tenant"))
    await session.commit()


async def _insert_tenant(session: AsyncSession, codigo: str = "test-tenant") -> tuple:
    """Insert a tenant, return (id, codigo)."""
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id, codigo"),
        {"c": codigo},
    )
    await session.commit()
    row = r.one()
    return row.id, row.codigo


async def _insert_user(
    session: AsyncSession,
    tid: uuid.UUID,
    email: str | None = None,
    password: str = "TestPass123!",
) -> tuple:
    """Insert a user via raw SQL, return (id, tid, email_plaintext)."""
    from app.core.encryption import encrypt, hmac_email  # noqa: PLC0415
    email = email or f"ausr-{uuid.uuid4().hex[:8]}@test.com"
    pw_hash = hash_password(password)
    result = await session.execute(
        text("""
            INSERT INTO "user" (tenant_id, email_cifrado, email_hash, password_hash, nombre, apellidos, is_2fa_enabled, is_active)
            VALUES (:tid, :ec, :eh, :ph, :n, :a, FALSE, TRUE)
            RETURNING id, tenant_id
        """),
        {
            "tid": tid,
            "ec": encrypt(email),
            "eh": hmac_email(email),
            "ph": pw_hash,
            "n": "First",
            "a": "Last",
        },
    )
    await session.commit()
    row = result.one()
    return row.id, row.tenant_id, email  # devolvemos email plaintext para pasarlo al login


async def _insert_user_with_2fa(
    session: AsyncSession,
    tid: uuid.UUID,
) -> tuple:
    """Insert a user with 2FA enabled."""
    from app.core.encryption import encrypt, hmac_email  # noqa: PLC0415
    secret = generate_totp_secret()
    email = f"2fa-{uuid.uuid4().hex[:8]}@test.com"
    pw_hash = hash_password("TestPass123!")
    result = await session.execute(
        text("""
            INSERT INTO "user" (tenant_id, email_cifrado, email_hash, password_hash, nombre, apellidos, is_2fa_enabled, totp_secret, is_active)
            VALUES (:tid, :ec, :eh, :ph, :n, :a, TRUE, :secret, TRUE)
            RETURNING id, tenant_id
        """),
        {
            "tid": tid,
            "ec": encrypt(email),
            "eh": hmac_email(email),
            "ph": pw_hash,
            "n": "First",
            "a": "Last",
            "secret": secret,
        },
    )
    await session.commit()
    row = result.one()
    return row.id, row.tenant_id, email, secret  # devolvemos email plaintext


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def auth_service(db_session: AsyncSession):
    """Create an AuthService with all repos for the test tenant."""
    tid, _ = await _insert_tenant(db_session)
    user_repo = UserRepository(db_session, tid)
    refresh_repo = RefreshTokenRepository(db_session, tid)
    recovery_repo = RecoveryTokenRepository(db_session, tid)
    service = AuthService(
        session=db_session,
        tenant_id=tid,
        user_repo=user_repo,
        refresh_repo=refresh_repo,
        recovery_repo=recovery_repo,
    )
    # Store tid for convenience
    service._test_tid = tid
    return service


# ── Login ─────────────────────────────────────────────────────────────


class TestLogin:
    """RED: AuthService.login() should fail before implementation."""

    @pytest.mark.asyncio
    async def test_login_success(self, db_session: AsyncSession):
        """login() returns tokens for valid credentials."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        result = await svc.login(codigo, email, "TestPass123!")
        assert "access_token" in result
        assert "refresh_token" in result
        assert "expires_in" in result

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, db_session: AsyncSession):
        """login() raises for wrong password."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        _, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        with pytest.raises(ValueError, match="Invalid email or password"):
            await svc.login(codigo, email, "WrongPassword1!")

    @pytest.mark.asyncio
    async def test_login_unknown_email(self, db_session: AsyncSession):
        """login() raises for unknown email."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        with pytest.raises(ValueError, match="Invalid email or password"):
            await svc.login(codigo, "nobody@example.com", "TestPass123!")

    @pytest.mark.asyncio
    async def test_login_inactive_user(self, db_session: AsyncSession):
        """login() raises for inactive user."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        from app.core.encryption import encrypt, hmac_email  # noqa: PLC0415
        pw_hash = hash_password("TestPass123!")
        email = f"inact-{uuid.uuid4().hex[:8]}@test.com"
        await db_session.execute(
            text("""
                INSERT INTO "user" (tenant_id, email_cifrado, email_hash, password_hash, nombre, apellidos, is_active, is_2fa_enabled)
                VALUES (:tid, :ec, :eh, :ph, :n, :a, FALSE, FALSE)
                RETURNING id
            """),
            {
                "tid": tid,
                "ec": encrypt(email),
                "eh": hmac_email(email),
                "ph": pw_hash,
                "n": "In",
                "a": "Active",
            },
        )
        await db_session.commit()
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        with pytest.raises(ValueError, match="Account is inactive"):
            await svc.login(codigo, email, "TestPass123!")

    @pytest.mark.asyncio
    async def test_login_rate_limited(self, db_session: AsyncSession):
        """login() raises after too many attempts."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        _, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
            max_attempts=3,
        )
        # Use a wrong password to accumulate attempts
        for _ in range(3):
            with pytest.raises(ValueError):
                await svc.login(codigo, email, "WrongPass1!")
        # 4th should be rate limited (distinct message)
        with pytest.raises(ValueError, match="Too many login attempts"):
            await svc.login(codigo, email, "TestPass123!")

    @pytest.mark.asyncio
    async def test_login_unknown_tenant_code(self, db_session: AsyncSession):
        """login() raises for unknown tenant code."""
        await _ensure_tables(db_session)
        tid = uuid.uuid4()
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        with pytest.raises(ValueError, match="Invalid email or password"):
            await svc.login("nonexistent", "a@b.com", "TestPass123!")

    @pytest.mark.asyncio
    async def test_login_2fa_required(self, db_session: AsyncSession):
        """login() returns session_token when 2FA is enabled."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        _, _, email, _ = await _insert_user_with_2fa(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        result = await svc.login(codigo, email, "TestPass123!")
        assert result.get("requires_2fa") is True
        assert "session_token" in result
        assert "access_token" not in result  # not yet issued


# ── 2FA ────────────────────────────────────────────────────────────────


class TestTwoFA:
    """RED: AuthService 2FA methods."""

    @pytest.mark.asyncio
    async def test_enroll_2fa(self, db_session: AsyncSession):
        """enroll_2fa() returns secret and URI."""
        await _ensure_tables(db_session)
        tid, _ = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        result = await svc.enroll_2fa(uid)
        assert "secret" in result
        assert "uri" in result
        assert result["uri"].startswith("otpauth://totp/")

    @pytest.mark.asyncio
    async def test_enable_2fa_with_valid_code(self, db_session: AsyncSession):
        """enable_2fa() verifies code and enables 2FA."""
        await _ensure_tables(db_session)
        tid, _ = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        enroll = await svc.enroll_2fa(uid)
        # Generate a valid code using pyotp
        import pyotp
        totp = pyotp.TOTP(enroll["secret"])
        code = totp.now()
        await svc.enable_2fa(uid, code)
        # Now user should have 2FA enabled
        user = await UserRepository(db_session, tid).get_by_id(uid)
        assert user is not None
        assert user.is_2fa_enabled is True

    @pytest.mark.asyncio
    async def test_enable_2fa_invalid_code(self, db_session: AsyncSession):
        """enable_2fa() raises for invalid code."""
        await _ensure_tables(db_session)
        tid, _ = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        await svc.enroll_2fa(uid)
        with pytest.raises(ValueError, match="Invalid TOTP code"):
            await svc.enable_2fa(uid, "000000")

    @pytest.mark.asyncio
    async def test_verify_2fa_login(self, db_session: AsyncSession):
        """verify_2fa_login() issues tokens after valid code."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        _, _, email, secret = await _insert_user_with_2fa(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        login_result = await svc.login(codigo, email, "TestPass123!")
        session_token = login_result["session_token"]
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        result = await svc.verify_2fa_login(session_token, code)
        assert "access_token" in result
        assert "refresh_token" in result

    @pytest.mark.asyncio
    async def test_verify_2fa_login_invalid_code(self, db_session: AsyncSession):
        """verify_2fa_login() raises for invalid code."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        _, _, email, _ = await _insert_user_with_2fa(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        login_result = await svc.login(codigo, email, "TestPass123!")
        with pytest.raises(ValueError, match="Invalid TOTP code"):
            await svc.verify_2fa_login(login_result["session_token"], "000000")


# ── Refresh ────────────────────────────────────────────────────────────


class TestRefresh:
    """RED: AuthService.refresh()."""

    @pytest.mark.asyncio
    async def test_refresh_rotates_token(self, db_session: AsyncSession):
        """refresh() returns new tokens and revokes old one."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        login = await svc.login(codigo, email, "TestPass123!")
        old_token = login["refresh_token"]
        result = await svc.refresh(old_token)
        assert "access_token" in result
        assert "refresh_token" in result
        assert result["refresh_token"] != old_token

    @pytest.mark.asyncio
    async def test_refresh_revoked_token(self, db_session: AsyncSession):
        """refresh() raises for revoked token and revokes family."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        login = await svc.login(codigo, email, "TestPass123!")
        token = login["refresh_token"]
        # Revoke it manually via repo
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        repo = RefreshTokenRepository(db_session, tid)
        found = await repo.get_by_hash(token_hash)
        assert found is not None
        await repo.revoke(found.id)
        with pytest.raises(ValueError, match="Refresh token has been revoked"):
            await svc.refresh(token)

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self, db_session: AsyncSession):
        """refresh() raises for expired token."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        login = await svc.login(codigo, email, "TestPass123!")
        token = login["refresh_token"]
        # Expire the token by updating expires_at in DB
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        await db_session.execute(
            text("UPDATE refresh_token SET expires_at = :exp WHERE token_hash = :th"),
            {"exp": datetime.now(timezone.utc) - timedelta(hours=1), "th": token_hash},
        )
        await db_session.commit()
        db_session.expunge_all()
        with pytest.raises(ValueError, match="Refresh token has expired"):
            await svc.refresh(token)


# ── Logout ─────────────────────────────────────────────────────────────


class TestLogout:
    """RED: AuthService.logout()."""

    @pytest.mark.asyncio
    async def test_logout_revokes_token(self, db_session: AsyncSession):
        """logout() revokes the given refresh token."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        login = await svc.login(codigo, email, "TestPass123!")
        await svc.logout(login["refresh_token"])
        # Verify token is revoked
        token_hash = hashlib.sha256(login["refresh_token"].encode()).hexdigest()
        repo = RefreshTokenRepository(db_session, tid)
        found = await repo.get_by_hash(token_hash)
        assert found is not None
        assert found.revoked_at is not None

    @pytest.mark.asyncio
    async def test_logout_no_token_ok(self, db_session: AsyncSession):
        """logout() does not raise when called without a token."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        # Just don't raise
        await svc.logout(None)


# ── Forgot / Reset Password ──────────────────────────────────────────


class TestForgotReset:
    """RED: AuthService forgot/reset password."""

    @pytest.mark.asyncio
    async def test_forgot_creates_recovery_token(self, db_session: AsyncSession):
        """forgot_password() creates a recovery token."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        token = await svc.forgot_password(codigo, email)
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.asyncio
    async def test_forgot_unknown_email_returns_none(self, db_session: AsyncSession):
        """forgot_password() returns None for unknown email (don't leak info)."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        result = await svc.forgot_password(codigo, "nobody@example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_reset_password_success(self, db_session: AsyncSession):
        """reset_password() changes password for valid token."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        token = await svc.forgot_password(codigo, email)
        assert token is not None
        await svc.reset_password(token, "NewPassword456!")
        # Verify new password works
        result = await svc.login(codigo, email, "NewPassword456!")
        assert "access_token" in result

    @pytest.mark.asyncio
    async def test_reset_password_used_token(self, db_session: AsyncSession):
        """reset_password() raises for already-used token."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        token = await svc.forgot_password(codigo, email)
        assert token is not None
        await svc.reset_password(token, "NewPassword456!")
        with pytest.raises(ValueError, match="Invalid or expired recovery token"):
            await svc.reset_password(token, "AnotherPass789!")


# ── Change Password ──────────────────────────────────────────────────


class TestChangePassword:
    """RED: AuthService.change_password()."""

    @pytest.mark.asyncio
    async def test_change_password_success(self, db_session: AsyncSession):
        """change_password() changes password when old is correct."""
        await _ensure_tables(db_session)
        tid, codigo = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        await svc.change_password(uid, "TestPass123!", "NewPass456!")
        # Login with new password
        result = await svc.login(codigo, email, "NewPass456!")
        assert "access_token" in result

    @pytest.mark.asyncio
    async def test_change_password_wrong_old(self, db_session: AsyncSession):
        """change_password() raises when old password is wrong."""
        await _ensure_tables(db_session)
        tid, _ = await _insert_tenant(db_session)
        uid, _, email = await _insert_user(db_session, tid)
        svc = AuthService(
            session=db_session,
            tenant_id=tid,
            user_repo=UserRepository(db_session, tid),
            refresh_repo=RefreshTokenRepository(db_session, tid),
            recovery_repo=RecoveryTokenRepository(db_session, tid),
        )
        with pytest.raises(ValueError, match="Current password is incorrect"):
            await svc.change_password(uid, "WrongPass1!", "NewPass456!")
