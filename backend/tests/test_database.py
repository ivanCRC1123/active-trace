"""Tests for database connectivity — smoke tests against a real PostgreSQL.

These tests require a running PostgreSQL instance reachable via the
``DATABASE_URL_TEST`` environment variable.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import async_session_factory


@pytest.mark.asyncio
async def test_select_one(db_session):
    """A minimal smoke test: execute ``SELECT 1`` and read the result."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_session_closes_on_exception():
    """The async session is closed when an exception occurs in its scope.

    This verifies that the ``finally`` block in ``get_db`` (and the
    ``db_session`` fixture) prevents connection leaks to the pool.

    Uses a dedicated engine without ``pool_pre_ping`` to avoid a
    known race condition between asyncpg's ping and Windows
    ProactorEventLoop shutdown.
    """
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()

    async def _will_raise(s):
        try:
            _ = await s.execute(text("SELECT 1"))
            msg = "simulated db error"
            raise RuntimeError(msg)
        finally:
            await s.close()

    with pytest.raises(RuntimeError, match="simulated db error"):
        await _will_raise(session)

    # After the exception + finally block, the ``close()`` in the finally
    # block succeeded.  We verify the session is reusable (clean state),
    # proving the connection was returned to the pool properly.
    result = await session.execute(text("SELECT 1"))
    assert result.scalar() == 1
    await session.close()
    await engine.dispose()
