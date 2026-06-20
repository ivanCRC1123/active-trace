"""Tests for UserRepository."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import hmac_email
from app.models.user import User
from app.repositories.user_repository import UserRepository

# DDL mirrors current ORM model (no-op if DB already migrated)
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


async def _ensure_tables(session: AsyncSession):
    """Create table if not exists and clean tenant data."""
    await session.execute(USER_DDL)
    await session.execute(text("DELETE FROM tenant"))
    await session.commit()


async def _insert_tenant(session: AsyncSession, codigo: str = "user-repo") -> uuid.UUID:
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id"),
        {"c": codigo},
    )
    await session.commit()
    return r.scalar_one()


@pytest.mark.asyncio
async def test_get_by_email_hash_found(db_session: AsyncSession):
    """get_by_email_hash returns the user when email matches."""
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = UserRepository(db_session, tid)
    # Pass plaintext — TypeDecorator encrypts on write
    user = await repo.create({
        "email_cifrado": "findme@test.com",
        "email_hash": hmac_email("findme@test.com"),
        "password_hash": "hash123",
        "nombre": "Find",
        "apellidos": "Me",
    })
    found = await repo.get_by_email_hash("findme@test.com")
    assert found is not None
    assert found.id == user.id


@pytest.mark.asyncio
async def test_get_by_email_hash_not_found(db_session: AsyncSession):
    """get_by_email_hash returns None when email does not exist."""
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = UserRepository(db_session, tid)
    found = await repo.get_by_email_hash("nonexistent@test.com")
    assert found is None


@pytest.mark.asyncio
async def test_get_by_email_hash_case_insensitive(db_session: AsyncSession):
    """get_by_email_hash is case-insensitive via hmac_email normalisation."""
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = UserRepository(db_session, tid)
    user = await repo.create({
        "email_cifrado": "CaseMix@Test.Com",
        "email_hash": hmac_email("CaseMix@Test.Com"),  # normalised to lowercase by hmac_email
        "password_hash": "hash",
        "nombre": "A",
        "apellidos": "B",
    })
    # Lookup with lowercase — hmac_email normalises both, hashes match
    found = await repo.get_by_email_hash("casemix@test.com")
    assert found is not None
    assert found.id == user.id


@pytest.mark.asyncio
async def test_tenant_isolation(db_session: AsyncSession):
    """User from tenant A not visible from tenant B repo."""
    await _ensure_tables(db_session)
    tid_a = await _insert_tenant(db_session, "iso-a")
    tid_b = await _insert_tenant(db_session, "iso-b")

    repo_a = UserRepository(db_session, tid_a)
    user_a = await repo_a.create({
        "email_cifrado": "user_a@test.com",
        "email_hash": hmac_email("user_a@test.com"),
        "password_hash": "hash",
        "nombre": "A",
        "apellidos": "A",
    })

    repo_b = UserRepository(db_session, tid_b)
    # get_by_email_hash from tenant B should not find tenant A's user
    found_b = await repo_b.get_by_email_hash("user_a@test.com")
    assert found_b is None

    # But should still work from tenant A
    found_a = await repo_a.get_by_email_hash("user_a@test.com")
    assert found_a is not None
