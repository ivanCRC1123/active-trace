"""Tests for RecoveryToken ORM model."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.recovery_token import RecoveryToken
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def _ensure_tables(db_session: AsyncSession):
    """Create required tables, clean tenant before each test."""
    for table in (User.__table__, RecoveryToken.__table__):
        async with db_session.bind.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=[table])
    await db_session.execute(text("TRUNCATE TABLE tenant CASCADE"))
    await db_session.commit()


async def _insert_tenant(session: AsyncSession) -> uuid.UUID:
    """Insert a tenant row, return its id."""
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id"),
        {"c": "recovery-test"},
    )
    await session.commit()
    return r.scalar_one()


async def _create_user(session: AsyncSession, tid: uuid.UUID) -> User:
    """Create and return a test user."""
    user = User(
        tenant_id=tid,
        email=f"rec-{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        nombre="Test",
        apellido="User",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


# ── RED: create RecoveryToken ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_recovery_token(db_session: AsyncSession):
    """Create RecoveryToken with user_id, tenant_id, token_hash, expires_at."""
    tid = await _insert_tenant(db_session)
    user = await _create_user(db_session, tid)

    token = RecoveryToken(
        user_id=user.id,
        tenant_id=tid,
        token_hash="c" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(token)
    await db_session.flush()
    await db_session.refresh(token)

    assert token.id is not None
    assert isinstance(token.id, uuid.UUID)
    assert token.token_hash == "c" * 64
    assert token.used_at is None


@pytest.mark.asyncio
async def test_unique_token_hash(db_session: AsyncSession):
    """Unique constraint on token_hash."""
    tid = await _insert_tenant(db_session)
    user = await _create_user(db_session, tid)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)

    t1 = RecoveryToken(
        user_id=user.id, tenant_id=tid,
        token_hash="uniquecheck", expires_at=expires,
    )
    db_session.add(t1)
    await db_session.flush()

    t2 = RecoveryToken(
        user_id=user.id, tenant_id=tid,
        token_hash="uniquecheck", expires_at=expires,
    )
    db_session.add(t2)
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_fk_to_tenant(db_session: AsyncSession):
    """FK to tenant is required."""
    tid = await _insert_tenant(db_session)
    user = await _create_user(db_session, tid)
    token = RecoveryToken(
        user_id=user.id,
        tenant_id=uuid.uuid4(),  # non-existent tenant
        token_hash="d" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db_session.add(token)
    with pytest.raises(Exception):
        await db_session.flush()
