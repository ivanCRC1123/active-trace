"""Tests for RefreshTokenRepository."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository

# DDL for user + refresh_token tables
RT_DDL = text("""
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


async def _ensure_tables(session: AsyncSession):
    """Create tables, clean data."""
    await session.execute(RT_DDL)
    await session.execute(REFRESH_DDL)
    await session.execute(text("DELETE FROM tenant"))
    await session.commit()


async def _insert_tenant(session: AsyncSession) -> uuid.UUID:
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id"),
        {"c": "rt-repo"},
    )
    await session.commit()
    return r.scalar_one()


async def _create_user(session: AsyncSession, tid: uuid.UUID) -> User:
    result = await session.execute(
        text("""
            INSERT INTO "user" (tenant_id, email, password_hash, nombre, apellido, is_2fa_enabled, is_active)
            VALUES (:tid, :email, :ph, :n, :a, FALSE, TRUE)
            RETURNING id, tenant_id, email
        """),
        {"tid": tid, "email": f"rtr-{uuid.uuid4().hex[:6]}@test.com",
         "ph": "hash", "n": "T", "a": "Repo"},
    )
    await session.commit()
    row = result.one()
    # Build a User ORM instance
    user = User(
        id=row.id, tenant_id=row.tenant_id, email=row.email,
        password_hash="hash", nombre="T", apellido="Repo",
    )
    return user


# ── get_by_hash ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_by_hash_found(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RefreshTokenRepository(db_session, tid)
    user = await _create_user(db_session, tid)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    token = await repo.create({
        "user_id": user.id, "token_hash": "a" * 64,
        "family_id": uuid.uuid4(), "expires_at": expires,
    })
    found = await repo.get_by_hash("a" * 64)
    assert found is not None
    assert found.id == token.id


@pytest.mark.asyncio
async def test_get_by_hash_not_found(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RefreshTokenRepository(db_session, tid)
    found = await repo.get_by_hash("nonexistent" + "b" * 55)
    assert found is None


# ── revoke ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_sets_revoked_at(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RefreshTokenRepository(db_session, tid)
    user = await _create_user(db_session, tid)
    expires = datetime.now(timezone.utc) + timedelta(days=7)
    token = await repo.create({
        "user_id": user.id, "token_hash": "b" * 64,
        "family_id": uuid.uuid4(), "expires_at": expires,
    })
    await repo.revoke(token.id)
    found = await repo.get_by_hash("b" * 64)
    assert found is not None
    assert found.revoked_at is not None


# ── revoke_family ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_family_revokes_all_in_family(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RefreshTokenRepository(db_session, tid)
    user = await _create_user(db_session, tid)
    family = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    t1 = await repo.create({
        "user_id": user.id, "token_hash": "x" * 64,
        "family_id": family, "expires_at": expires,
    })
    t2 = await repo.create({
        "user_id": user.id, "token_hash": "y" * 64,
        "family_id": family, "expires_at": expires,
    })

    count = await repo.revoke_family(family)
    assert count >= 2
    for f_id in (t1.id, t2.id):
        found = await repo.get_by_id(f_id)
        assert found.revoked_at is not None


# ── find_valid_by_user_id ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_find_valid_by_user_id(db_session: AsyncSession):
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = RefreshTokenRepository(db_session, tid)
    user = await _create_user(db_session, tid)
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    t1 = await repo.create({
        "user_id": user.id, "token_hash": "v1" + "v" * 62,
        "family_id": uuid.uuid4(), "expires_at": expires,
    })
    t2 = await repo.create({
        "user_id": user.id, "token_hash": "v2" + "v" * 62,
        "family_id": uuid.uuid4(), "expires_at": expires,
    })
    await repo.revoke(t2.id)

    valid = await repo.find_valid_by_user_id(user.id)
    ids = [t.id for t in valid]
    assert t1.id in ids
    assert t2.id not in ids
