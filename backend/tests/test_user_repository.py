"""Tests for UserRepository."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user_repository import UserRepository

# DDL for user table (mirrors ORM model)
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
async def test_get_by_email_found(db_session: AsyncSession):
    """get_by_email returns the user when email matches."""
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = UserRepository(db_session, tid)
    user = await repo.create({
        "email": "findme@test.com",
        "password_hash": "hash123",
        "nombre": "Find",
        "apellido": "Me",
    })
    found = await repo.get_by_email("findme@test.com")
    assert found is not None
    assert found.id == user.id


@pytest.mark.asyncio
async def test_get_by_email_not_found(db_session: AsyncSession):
    """get_by_email returns None when email does not exist."""
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = UserRepository(db_session, tid)
    found = await repo.get_by_email("nonexistent@test.com")
    assert found is None


@pytest.mark.asyncio
async def test_get_by_email_case_insensitive(db_session: AsyncSession):
    """get_by_email is case-insensitive."""
    await _ensure_tables(db_session)
    tid = await _insert_tenant(db_session)
    repo = UserRepository(db_session, tid)
    user = await repo.create({
        "email": "CaseMix@Test.Com",
        "password_hash": "hash",
        "nombre": "A",
        "apellido": "B",
    })
    found = await repo.get_by_email("casemix@test.com")
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
        "email": "user_a@test.com",
        "password_hash": "hash",
        "nombre": "A",
        "apellido": "A",
    })

    repo_b = UserRepository(db_session, tid_b)
    # get_by_email from tenant B should not find tenant A's user
    found_b = await repo_b.get_by_email("user_a@test.com")
    assert found_b is None

    # But should still work from tenant A
    found_a = await repo_a.get_by_email("user_a@test.com")
    assert found_a is not None
