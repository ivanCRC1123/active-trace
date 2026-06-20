"""Tests for RefreshToken ORM model."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.encryption import encrypt, hmac_email
from app.models.refresh_token import RefreshToken
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def _ensure_tables(db_session: AsyncSession):
    """Create required tables, clean tenant before each test."""
    for table in (User.__table__, RefreshToken.__table__):
        async with db_session.bind.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=[table])
    await db_session.execute(text("TRUNCATE TABLE tenant CASCADE"))
    await db_session.commit()


async def _insert_tenant(session: AsyncSession) -> uuid.UUID:
    """Insert a tenant row, return its id."""
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id"),
        {"c": "rt-test"},
    )
    await session.commit()
    return r.scalar_one()


async def _create_user(session: AsyncSession, tid: uuid.UUID) -> User:
    """Create and return a test user."""
    email = f"rt-{uuid.uuid4().hex[:6]}@test.com"
    user = User(
        tenant_id=tid,
        email_cifrado=encrypt(email),
        email_hash=hmac_email(email),
        password_hash="hash",
        nombre="Test",
        apellidos="User",
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


# ── RED: create RefreshToken ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_refresh_token(db_session: AsyncSession):
    """Create RefreshToken with user_id, token_hash, family_id, expires_at."""
    tid = await _insert_tenant(db_session)
    user = await _create_user(db_session, tid)

    family = uuid.uuid4()
    token = RefreshToken(
        tenant_id=tid,
        user_id=user.id,
        token_hash="a" * 64,
        family_id=family,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(token)
    await db_session.flush()
    await db_session.refresh(token)

    assert token.id is not None
    assert isinstance(token.id, uuid.UUID)
    assert token.token_hash == "a" * 64
    assert token.family_id == family
    assert token.revoked_at is None


@pytest.mark.asyncio
async def test_unique_token_hash(db_session: AsyncSession):
    """Unique constraint on token_hash."""
    tid = await _insert_tenant(db_session)
    user = await _create_user(db_session, tid)
    family = uuid.uuid4()
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    t1 = RefreshToken(
        tenant_id=tid, user_id=user.id, token_hash="samehash",
        family_id=family, expires_at=expires,
    )
    db_session.add(t1)
    await db_session.flush()

    t2 = RefreshToken(
        tenant_id=tid, user_id=user.id, token_hash="samehash",
        family_id=uuid.uuid4(), expires_at=expires,
    )
    db_session.add(t2)
    with pytest.raises(Exception):
        await db_session.flush()


@pytest.mark.asyncio
async def test_fk_to_user(db_session: AsyncSession):
    """FK to user is required."""
    tid = await _insert_tenant(db_session)
    token = RefreshToken(
        tenant_id=tid,
        user_id=uuid.uuid4(),  # non-existent user
        token_hash="b" * 64,
        family_id=uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(token)
    with pytest.raises(Exception):
        await db_session.flush()
