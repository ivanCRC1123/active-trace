"""Tests for User ORM model."""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import Base
from app.core.encryption import hmac_email
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def _ensure_tables(db_session: AsyncSession):
    """Create user table, clean tenant before each test."""
    from app.models.user import User  # noqa: PLC0415
    async with db_session.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    await db_session.execute(text("TRUNCATE TABLE tenant CASCADE"))
    await db_session.commit()


async def _insert_tenant(session: AsyncSession, codigo: str = "test-tenant") -> uuid.UUID:
    """Insert a tenant row, return its id."""
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id"),
        {"c": codigo},
    )
    await session.commit()
    return r.scalar_one()


# ── RED: create User ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession):
    """Create User — email_cifrado stores plaintext; TypeDecorator encrypts transparently."""
    tid = await _insert_tenant(db_session)
    user = User(
        tenant_id=tid,
        email_cifrado="test@example.com",    # TypeDecorator encrypts on write, decrypts on read
        email_hash=hmac_email("test@example.com"),
        password_hash="argon2hash123",
        nombre="Juan",
        apellidos="Perez",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)
    assert user.email_cifrado == "test@example.com"
    assert user.nombre == "Juan"
    assert user.apellidos == "Perez"


@pytest.mark.asyncio
async def test_user_defaults(db_session: AsyncSession):
    """Verify default values for is_2fa_enabled, is_active."""
    tid = await _insert_tenant(db_session)
    user = User(
        tenant_id=tid,
        email_cifrado="defaults@test.com",
        email_hash=hmac_email("defaults@test.com"),
        password_hash="hash",
        nombre="A",
        apellidos="B",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.is_2fa_enabled is False
    assert user.is_active is True
    assert user.totp_secret is None


@pytest.mark.asyncio
async def test_user_uuid_generated(db_session: AsyncSession):
    """Verify UUID generation on create."""
    tid = await _insert_tenant(db_session)
    user = User(
        tenant_id=tid,
        email_cifrado="uuid@test.com",
        email_hash=hmac_email("uuid@test.com"),
        password_hash="hash",
        nombre="A",
        apellidos="B",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)


# ── RED: unique (tenant_id, email_hash) constraint ────────────────────────


@pytest.mark.asyncio
async def test_email_unique_constraint(db_session: AsyncSession):
    """Duplicate (tenant_id, email_hash) raises integrity error."""
    tid = await _insert_tenant(db_session)
    user1 = User(
        tenant_id=tid,
        email_cifrado="duplicate@test.com",
        email_hash=hmac_email("duplicate@test.com"),
        password_hash="hash",
        nombre="A",
        apellidos="B",
    )
    db_session.add(user1)
    await db_session.flush()

    user2 = User(
        tenant_id=tid,
        email_cifrado="duplicate@test.com",
        email_hash=hmac_email("duplicate@test.com"),
        password_hash="hash2",
        nombre="C",
        apellidos="D",
    )
    db_session.add(user2)
    with pytest.raises(Exception):  # IntegrityError
        await db_session.flush()


# ── TRIANGULATE: soft delete, blind index lowercase normalisation ─────────


@pytest.mark.asyncio
async def test_user_soft_delete(db_session: AsyncSession):
    """Soft delete sets deleted_at."""
    tid = await _insert_tenant(db_session)
    user = User(
        tenant_id=tid,
        email_cifrado="softdel@test.com",
        email_hash=hmac_email("softdel@test.com"),
        password_hash="hash",
        nombre="A",
        apellidos="B",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    from sqlalchemy.sql import func

    user.deleted_at = func.now()
    await db_session.flush()
    await db_session.refresh(user)
    assert user.deleted_at is not None


@pytest.mark.asyncio
async def test_email_blind_index_normalises_lowercase(db_session: AsyncSession):
    """hmac_email normalises to lowercase — same email different case → same hash."""
    h1 = hmac_email("UpperCase@TEST.com")
    h2 = hmac_email("uppercase@test.com")
    assert h1 == h2
