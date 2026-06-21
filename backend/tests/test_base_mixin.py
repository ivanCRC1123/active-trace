"""Tests for BaseEntityMixin — timestamps, soft delete, tenant scope.

Metadata tests (no DB) verify column existence.
DB tests use session-level DDL and unique codigo values.
"""

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.base import BaseEntityMixin

# ── Metadata-only tests (no DB needed) ────────────────────────────────


class _TestModel(Base, BaseEntityMixin):
    """Dummy model to verify mixin metadata."""
    __tablename__ = "_test_meta"
    label = sa.Column(sa.String(100))


class TestMixinMetadata:
    """Verify that BaseEntityMixin provides correct columns."""

    def test_has_all_mixin_columns(self):
        cols = _TestModel.__table__.columns
        assert "id" in cols
        assert "created_at" in cols
        assert "updated_at" in cols
        assert "tenant_id" in cols
        assert "deleted_at" in cols

    def test_id_is_uuid_type(self):
        col = _TestModel.__table__.columns["id"]
        assert isinstance(col.type, (sa.UUID, sa.types.Uuid)), (
            f"Got {type(col.type)}"
        )

    def test_tenant_id_column_exists_and_not_null(self):
        col = _TestModel.__table__.columns["tenant_id"]
        assert not col.nullable
        assert len(col.foreign_keys) > 0


# ── DB tests ─────────────────────────────────────────────────────────
# DDL goes through the session (single statements only) since
# PostgreSQL supports transactional DDL.

_CREATE_TENANT = text(
    "CREATE TABLE IF NOT EXISTS tenant ("
    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
    "nombre VARCHAR(255) NOT NULL, "
    "codigo VARCHAR(50) NOT NULL UNIQUE, "
    "estado VARCHAR(20) NOT NULL DEFAULT 'activo', "
    "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
    "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
    "deleted_at TIMESTAMPTZ)"
)
_CREATE_TEST = text(
    "CREATE TABLE IF NOT EXISTS _test_mixin ("
    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
    "label VARCHAR(100), "
    "tenant_id UUID NOT NULL REFERENCES tenant(id), "
    "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
    "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
    "deleted_at TIMESTAMPTZ)"
)
# Trigger function for auto-updating updated_at (also created in migration 001)
_CREATE_TRIGGER_FN = text(
    "CREATE OR REPLACE FUNCTION update_updated_at_column() "
    "RETURNS TRIGGER AS $$ "
    "BEGIN NEW.updated_at = NOW(); RETURN NEW; END; "
    "$$ LANGUAGE plpgsql"
)
_DROP_TRIGGER = text(
    "DROP TRIGGER IF EXISTS trg__test_mixin_updated_at ON _test_mixin"
)
_CREATE_TRIGGER = text(
    "CREATE TRIGGER trg__test_mixin_updated_at "
    "BEFORE UPDATE ON _test_mixin "
    "FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()"
)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_test_mixin(db_session: AsyncSession):
    """Remove _test_mixin rows after each DB test to avoid tenant FK violations."""
    yield
    try:
        await db_session.execute(text("DELETE FROM _test_mixin"))
        await db_session.commit()
    except Exception:
        await db_session.rollback()


@pytest.mark.asyncio
async def test_id_auto_generates_on_insert(db_session):
    """id is auto-generated when inserting a record."""
    await db_session.execute(_CREATE_TENANT)
    await db_session.execute(_CREATE_TEST)
    await db_session.commit()

    codigo = str(uuid.uuid4())[:8]
    result = await db_session.execute(
        text("INSERT INTO tenant (nombre, codigo) VALUES (:n, :c) RETURNING id"),
        {"n": "test", "c": codigo},
    )
    await db_session.commit()
    tenant_id = result.scalar_one()

    result = await db_session.execute(
        text(
            "INSERT INTO _test_mixin (label, tenant_id) "
            "VALUES (:l, :tid) RETURNING id"
        ),
        {"l": "auto-id", "tid": tenant_id},
    )
    await db_session.commit()
    row_id = result.scalar_one()
    assert row_id is not None


@pytest.mark.asyncio
async def test_created_at_and_updated_at_set_on_create(db_session):
    """created_at and updated_at are set when inserting."""
    await db_session.execute(_CREATE_TENANT)
    await db_session.execute(_CREATE_TEST)
    await db_session.commit()

    codigo = str(uuid.uuid4())[:8]
    result = await db_session.execute(
        text("INSERT INTO tenant (nombre, codigo) VALUES (:n, :c) RETURNING id"),
        {"n": "test", "c": codigo},
    )
    await db_session.commit()
    tenant_id = result.scalar_one()

    await db_session.execute(
        text(
            "INSERT INTO _test_mixin (label, tenant_id) "
            "VALUES (:l, :tid)"
        ),
        {"l": "ts-test", "tid": tenant_id},
    )
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT created_at, updated_at FROM _test_mixin WHERE label = :l"),
        {"l": "ts-test"},
    )
    rec = result.first()
    assert rec is not None
    created_at, updated_at = rec
    assert created_at is not None and isinstance(created_at, datetime)
    assert updated_at is not None and isinstance(updated_at, datetime)


@pytest.mark.asyncio
async def test_updated_at_changes_on_update(db_session):
    """updated_at is refreshed by trigger when a row is modified."""
    await db_session.execute(_CREATE_TENANT)
    await db_session.execute(_CREATE_TEST)
    await db_session.execute(_CREATE_TRIGGER_FN)
    await db_session.execute(_DROP_TRIGGER)
    await db_session.execute(_CREATE_TRIGGER)
    await db_session.commit()

    codigo = str(uuid.uuid4())[:8]
    result = await db_session.execute(
        text("INSERT INTO tenant (nombre, codigo) VALUES (:n, :c) RETURNING id"),
        {"n": "test", "c": codigo},
    )
    await db_session.commit()
    tenant_id = result.scalar_one()

    result = await db_session.execute(
        text(
            "INSERT INTO _test_mixin (label, tenant_id) "
            "VALUES (:l, :tid) RETURNING id, updated_at"
        ),
        {"l": "trigger-test", "tid": tenant_id},
    )
    await db_session.commit()
    row_id, updated_at_before = result.first()

    await db_session.execute(
        text("UPDATE _test_mixin SET label = :l WHERE id = :id"),
        {"l": "modified", "id": row_id},
    )
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT updated_at FROM _test_mixin WHERE id = :id"),
        {"id": row_id},
    )
    updated_at_after = result.scalar_one()

    assert updated_at_after > updated_at_before, (
        "updated_at should advance after modification"
    )


@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at(db_session):
    """Setting deleted_at = NOW() represents a soft delete."""
    await db_session.execute(_CREATE_TENANT)
    await db_session.execute(_CREATE_TEST)
    await db_session.commit()

    codigo = str(uuid.uuid4())[:8]
    result = await db_session.execute(
        text("INSERT INTO tenant (nombre, codigo) VALUES (:n, :c) RETURNING id"),
        {"n": "test", "c": codigo},
    )
    await db_session.commit()
    tenant_id = result.scalar_one()

    result = await db_session.execute(
        text(
            "INSERT INTO _test_mixin (label, tenant_id) "
            "VALUES (:l, :tid) RETURNING id"
        ),
        {"l": "soft-del-test", "tid": tenant_id},
    )
    await db_session.commit()
    row_id = result.scalar_one()

    # Verify deleted_at is NULL initially
    result = await db_session.execute(
        text("SELECT deleted_at FROM _test_mixin WHERE id = :id"),
        {"id": row_id},
    )
    assert result.scalar_one() is None

    # Soft-delete
    await db_session.execute(
        text("UPDATE _test_mixin SET deleted_at = NOW() WHERE id = :id"),
        {"id": row_id},
    )
    await db_session.commit()

    result = await db_session.execute(
        text("SELECT deleted_at FROM _test_mixin WHERE id = :id"),
        {"id": row_id},
    )
    deleted_at = result.scalar_one()
    assert deleted_at is not None
    assert isinstance(deleted_at, datetime)


@pytest.mark.asyncio
async def test_tenant_id_not_null_enforced(db_session):
    """Inserting without tenant_id violates NOT NULL constraint."""
    await db_session.execute(_CREATE_TENANT)
    await db_session.execute(_CREATE_TEST)
    await db_session.commit()

    with pytest.raises(Exception) as excinfo:
        await db_session.execute(
            text(
                "INSERT INTO _test_mixin (label) "
                "VALUES (:l)"
            ),
            {"l": "no-tenant"},
        )
        await db_session.commit()
    # The error message from PostgreSQL should mention null or not-null
    msg = str(excinfo.value).lower()
    assert any(w in msg for w in ("null", "not null", "violates", "tenant_id")), msg
