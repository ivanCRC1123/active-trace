"""Tests for Tenant model — creation, defaults, constraints, soft delete.

The ``tenant`` table is created by Alembic migration 001, so we do NOT
create it manually here — we only clean data before each test.
"""

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text


@pytest_asyncio.fixture(autouse=True)
async def _clean_tenant(db_session):
    """Clean tenant table before each test (table exists from migration)."""
    await db_session.execute(text("TRUNCATE TABLE tenant CASCADE"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_tenant_create(db_session):
    """Insert a tenant directly and verify columns."""
    result = await db_session.execute(
        text("""
            INSERT INTO tenant (codigo, nombre)
            VALUES ('test-01', 'Test Tenant')
            RETURNING id, codigo, nombre, estado, created_at, updated_at, deleted_at
        """)
    )
    row = result.one()
    assert isinstance(row.id, uuid.UUID)
    assert row.codigo == "test-01"
    assert row.nombre == "Test Tenant"
    assert row.estado == "activo"
    assert isinstance(row.created_at, datetime)
    assert isinstance(row.updated_at, datetime)
    assert row.deleted_at is None


@pytest.mark.asyncio
async def test_tenant_default_estado(db_session):
    """estado defaults to 'activo'."""
    result = await db_session.execute(
        text("""
            INSERT INTO tenant (codigo, nombre)
            VALUES ('test-02', 'Test Tenant 2')
            RETURNING estado
        """)
    )
    assert result.scalar_one() == "activo"


@pytest.mark.asyncio
async def test_tenant_codigo_unique_constraint(db_session):
    """Duplicate codigo raises an IntegrityError."""
    await db_session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES ('dup-codigo', 'First')")
    )
    await db_session.commit()

    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text("INSERT INTO tenant (codigo, nombre) VALUES ('dup-codigo', 'Second')")
        )
        await db_session.commit()

    msg = str(excinfo.value).lower()
    assert any(w in msg for w in ("unique", "duplicate", "already exists")), msg


@pytest.mark.asyncio
async def test_tenant_soft_delete(db_session):
    """Soft delete sets deleted_at."""
    result = await db_session.execute(
        text("""
            INSERT INTO tenant (codigo, nombre)
            VALUES ('softdel', 'To Delete')
            RETURNING id
        """)
    )
    tenant_id = result.scalar_one()
    await db_session.commit()

    # Soft delete
    await db_session.execute(
        text("UPDATE tenant SET deleted_at = now() WHERE id = :id"),
        {"id": tenant_id},
    )
    await db_session.commit()

    # Verify deleted_at is set
    row = (
        await db_session.execute(
            text("SELECT deleted_at FROM tenant WHERE id = :id"),
            {"id": tenant_id},
        )
    ).one()
    assert row.deleted_at is not None
    assert isinstance(row.deleted_at, datetime)
