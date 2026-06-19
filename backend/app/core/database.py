"""Database engine, session factory and declarative base.

Provides the async SQLAlchemy 2.0 engine (asyncpg), a session factory
(``async_sessionmaker``) and the ``Base`` declarative model class.

The engine is created at module level using the ``settings`` singleton.
For tests, call ``init_engine(url)`` before importing the module or
set ``DATABASE_URL`` env var. Sessions are request-scoped via the
``get_db`` dependency (see ``dependencies.py``).
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, Pool

from app.core.config import settings

# ── Globals (set by init_engine) ────────────────────────────────────

engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


# ── Declarative base ────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# ── Engine initialisation ───────────────────────────────────────────


def init_engine(url: str | None = None, poolclass: type[Pool] | None = None) -> None:
    """Create or re-create the async engine and session factory.

    If ``url`` is ``None``, the value from ``settings.DATABASE_URL``
    is used.  Call this explicitly in tests with a test DB URL.

    ``poolclass`` defaults to ``None`` (SQLAlchemy's default pool,
    ``AsyncAdaptedQueuePool``).  Pass ``NullPool`` for test environments
    where event loops may change between sessions (e.g. Windows).
    """
    global engine, async_session_factory
    db_url = url or settings.DATABASE_URL
    engine = create_async_engine(
        db_url,
        pool_pre_ping=poolclass is None,
        echo=False,
        poolclass=poolclass,
    )
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# Initialise with the production URL on import.
init_engine()
