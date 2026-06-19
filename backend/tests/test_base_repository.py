"""Tests for BaseRepository — CRUD, soft delete, multi-tenant isolation.

Uses a test ORM model that inherits ``BaseEntityMixin``. The fixture
creates only ``_test_scoped`` (test-only table); ``tenant`` already
exists from Alembic migration 001.
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import BaseEntityMixin
from app.repositories.base import BaseRepository


# ── Test ORM model (tenant_id FK → tenant.id) ────────────────────────


class _TestScoped(Base, BaseEntityMixin):
    """Minimal model with tenant_id — used ONLY for repository tests."""
    __tablename__ = "_test_scoped"
    label: Mapped[str] = mapped_column(String(100), nullable=True)


# ── DDL for both tables ───────────────────────────────────────────────


SCOPED_DDL = text("""
    CREATE TABLE IF NOT EXISTS _test_scoped (
        id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        label       VARCHAR(100),
        tenant_id   UUID NOT NULL REFERENCES tenant(id),
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at  TIMESTAMPTZ
    )
""")


# ── Fixture ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _ensure_tables(db_session):
    """Create _test_scoped (test-only), clean data before each test.

    The ``tenant`` table already exists from Alembic migration 001;
    we only create ``_test_scoped`` here.  ``TRUNCATE tenant CASCADE``
    also empties ``_test_scoped`` due to the FK, so we don't need a
    separate truncate for it.
    """
    await db_session.execute(SCOPED_DDL)
    await db_session.execute(text("TRUNCATE TABLE tenant CASCADE"))
    await db_session.commit()


# ── Helper ────────────────────────────────────────────────────────────


def _make_repo(session, tenant_id):
    """Build a ``BaseRepository[_TestScoped]`` via subclass."""
    class ScopedRepo(BaseRepository[_TestScoped]):
        @property
        def model_class(self):
            return _TestScoped

    return ScopedRepo(session, tenant_id)


async def _insert_tenant(session, codigo):
    """Insert a tenant row, return its id."""
    r = await session.execute(
        text("INSERT INTO tenant (codigo, nombre) VALUES (:c, :c) RETURNING id"),
        {"c": codigo},
    )
    await session.commit()
    return r.scalar_one()


# ── Tests: create ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_assigns_tenant_id(db_session):
    """Repository.create() assigns the tenant_id automatically."""
    tid = await _insert_tenant(db_session, "cr-01")
    repo = _make_repo(db_session, tid)

    entity = _TestScoped(label="create-test")
    created = await repo.create(entity)
    assert created.tenant_id == tid


@pytest.mark.asyncio
async def test_create_from_dict(db_session):
    """Repository.create() accepts a dict and returns a model."""
    tid = await _insert_tenant(db_session, "cr-02")
    repo = _make_repo(db_session, tid)

    created = await repo.create({"label": "from-dict"})
    assert created.label == "from-dict"
    assert created.tenant_id == tid


# ── Tests: list ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_only_active_for_tenant(db_session):
    """list() returns only non-deleted records of the correct tenant."""
    tid_a = await _insert_tenant(db_session, "list-a")
    repo_a = _make_repo(db_session, tid_a)
    await repo_a.create({"label": "a-1"})

    tid_b = await _insert_tenant(db_session, "list-b")
    repo_b = _make_repo(db_session, tid_b)
    await repo_b.create({"label": "b-1"})

    items_a = await repo_a.list()
    assert len(items_a) == 1
    assert items_a[0].label == "a-1"


# ── Tests: get_by_id ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_by_id_returns_record_for_correct_tenant(db_session):
    """get_by_id() returns the record if it belongs to the tenant."""
    tid = await _insert_tenant(db_session, "get-01")
    repo = _make_repo(db_session, tid)
    created = await repo.create({"label": "get-test"})

    found = await repo.get_by_id(created.id)
    assert found is not None
    assert found.id == created.id


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_wrong_tenant(db_session):
    """get_by_id() returns None if the record belongs to another tenant."""
    tid_a = await _insert_tenant(db_session, "get-02")
    tid_b = await _insert_tenant(db_session, "get-03")
    repo_a = _make_repo(db_session, tid_a)
    created = await repo_a.create({"label": "other-tenant"})

    repo_b = _make_repo(db_session, tid_b)
    found = await repo_b.get_by_id(created.id)
    assert found is None


# ── Tests: update ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_modifies_and_returns(db_session):
    """update() changes field values and returns the updated record."""
    tid = await _insert_tenant(db_session, "upd-01")
    repo = _make_repo(db_session, tid)
    created = await repo.create({"label": "before"})

    updated = await repo.update(created.id, {"label": "after"})
    assert updated is not None
    assert updated.label == "after"


# ── Tests: soft_delete ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at_and_excludes_from_list(db_session):
    """soft_delete() sets deleted_at; list() excludes the record."""
    tid = await _insert_tenant(db_session, "del-01")
    repo = _make_repo(db_session, tid)
    created = await repo.create({"label": "to-delete"})

    result = await repo.soft_delete(created.id)
    assert result is True

    active = await repo.list()
    assert created.id not in {r.id for r in active}


@pytest.mark.asyncio
async def test_soft_delete_of_nonexistent_returns_false(db_session):
    """soft_delete() of a non-existent id returns False."""
    tid = await _insert_tenant(db_session, "del-02")
    repo = _make_repo(db_session, tid)
    result = await repo.soft_delete(uuid.uuid4())
    assert result is False


@pytest.mark.asyncio
async def test_list_with_deleted_includes_soft_deleted(db_session):
    """list_with_deleted() includes records with deleted_at set."""
    tid = await _insert_tenant(db_session, "del-03")
    repo = _make_repo(db_session, tid)
    created = await repo.create({"label": "list-del"})
    await repo.soft_delete(created.id)

    all_records = await repo.list_with_deleted()
    assert created.id in {r.id for r in all_records}


# ── Critical: multi-tenant isolation ─────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_isolation_list(db_session):
    """list() of tenant A does NOT include records from tenant B."""
    tid_a = await _insert_tenant(db_session, "iso-a")
    tid_b = await _insert_tenant(db_session, "iso-b")
    repo_a = _make_repo(db_session, tid_a)
    repo_b = _make_repo(db_session, tid_b)

    await repo_a.create({"label": "iso-a1"})
    await repo_b.create({"label": "iso-b1"})

    list_a = await repo_a.list()
    list_b = await repo_b.list()

    a_labels = {r.label for r in list_a}
    b_labels = {r.label for r in list_b}

    assert "iso-b1" not in a_labels
    assert "iso-a1" not in b_labels


@pytest.mark.asyncio
async def test_tenant_isolation_get_by_id(db_session):
    """get_by_id() from repo A returns None for records of tenant B."""
    tid_a = await _insert_tenant(db_session, "iso-ga")
    tid_b = await _insert_tenant(db_session, "iso-gb")
    repo_a = _make_repo(db_session, tid_a)
    repo_b = _make_repo(db_session, tid_b)

    from_a = await repo_a.create({"label": "iso-get-a"})
    from_b = await repo_b.create({"label": "iso-get-b"})

    assert await repo_a.get_by_id(from_b.id) is None
    assert await repo_b.get_by_id(from_a.id) is None


# ── Verify no hard_delete ────────────────────────────────────────────


class TestNoHardDelete:
    """Verify that BaseRepository does NOT expose a hard_delete method."""

    def test_hard_delete_not_defined(self):
        assert not hasattr(BaseRepository, "hard_delete")
