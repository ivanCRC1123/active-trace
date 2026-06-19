"""Tests for RecoveryTokenRepository."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recovery_token import RecoveryToken
from app.repositories.recovery_token_repository import RecoveryTokenRepository

# DDL for user + recovery_token tables
USER_DDL = text("""
    CREATE TABLE IF NOT EXISTS "user" (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email           VARCHAR(255) NOT NULL UNIQUE,
        password_hash   VARCHAR(255) NOT NULL,
        nombre          VARCHAR(100) NOT NULL,
        apellido        VARCHAR(100) NOT NULL,
        is_2fa_enabled  BOOLEAN NOT NULL DEFAULT FALSE,
        totp_secret     TEXT,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
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
    await session.execute(USER_DDL)
    await session.execute(RECOVERY_DDL)
    await session.execute(text("DELETE FROM tenant"))
    await session.commit()


async def _insert_tenant(session: AsyncSession) -> uuid.UUID:
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id"),
        {"c": "recovery-repo"},
    )
    await session.commit()
    return r.scalar_one()


async def _create_user(session: AsyncSession, tid: uuid.UUID) -> tuple:
    """Create user via raw SQL, return (id, tid)."""
    result = await session.execute(
        text("""
            INSERT INTO "user" (tenant_id, email, password_hash, nombre, apellido, is_2fa_enabled, is_active)
            VALUES (:tid, :email, :ph, :n, :a, FALSE, TRUE)
            RETURNING id, tenant_id
        """),
        {"tid": tid, "email": f"recr-{uuid.uuid4().hex[:6]}@test.com",
         "ph": "hash", "n": "R", "a": "Repo"},
    )
    await session.commit()
    row = result.one()
    return row.id, row.tenant_id


# ── get_by_hash ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_by_hash_found(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RecoveryTokenRepository(db_session, tid)
    uid, _ = await _create_user(db_session, tid)
    token = await repo.create({
        "user_id": uid,
        "token_hash": "z" * 64,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
    })
    found = await repo.get_by_hash("z" * 64)
    assert found is not None
    assert found.id == token.id


@pytest.mark.asyncio
async def test_get_by_hash_not_found(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RecoveryTokenRepository(db_session, tid)
    found = await repo.get_by_hash("nonexistent" + "w" * 55)
    assert found is None


# ── mark_used ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_used_sets_used_at(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RecoveryTokenRepository(db_session, tid)
    uid, _ = await _create_user(db_session, tid)
    token = await repo.create({
        "user_id": uid,
        "token_hash": "m" * 64,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=15),
    })
    await repo.mark_used(token.id)
    found = await repo.get_by_hash("m" * 64)
    assert found is not None
    assert found.used_at is not None
