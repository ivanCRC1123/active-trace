"""Shared fixtures for all tests.

**Important**: environment defaults are set at module level *before*
any project imports so that the ``settings`` singleton in
``app.core.config`` is created with valid values.
"""

import os

# Set default environment variables BEFORE any project imports so the
# ``settings`` singleton (``config.py`` module level) loads valid values.
# Individual tests / CI overrides via ``DATABASE_URL_TEST``.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://trace:trace@localhost:5435/trace")
os.environ.setdefault("DATABASE_URL_TEST", "postgresql+asyncpg://trace:trace@localhost:5435/trace_test")
os.environ.setdefault("SECRET_KEY", "a" * 32)
os.environ.setdefault("ENCRYPTION_KEY", "b" * 32)
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "15")

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory, init_engine
from sqlalchemy.pool import NullPool


# ── Cleanup fixtures for tests that need to suppress defaults ──────


@pytest.fixture
def _clear_db_url(monkeypatch):
    """Remove DATABASE_URL from env so tests can verify missing field."""
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def _clear_secret_key(monkeypatch):
    """Remove SECRET_KEY from env so tests can verify missing field."""
    monkeypatch.delenv("SECRET_KEY", raising=False)


@pytest.fixture
def _clear_encryption_key(monkeypatch):
    """Remove ENCRYPTION_KEY from env so tests can verify missing field."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

# ── Database fixtures ───────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _setup_test_db():
    """Re-initialise the engine with the test database URL once per session.

    Priority: ``DATABASE_URL_TEST`` env var → ``settings.DATABASE_URL_TEST``
    → ``settings.DATABASE_URL``.
    """
    test_url = (
        os.environ.get("DATABASE_URL_TEST")
        or settings.DATABASE_URL_TEST
        or settings.DATABASE_URL
    )
    init_engine(test_url, poolclass=NullPool)
    return test_url


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async session for each test.

    Lazily imports ``async_session_factory`` to always get the *current*
    value (``init_engine`` may have been called again after the module-level
    ``from … import``, which would leave a stale reference).
    """
    from app.core import database as db_mod  # noqa: PLC0415 — live ref

    factory = db_mod.async_session_factory
    if factory is None:
        raise RuntimeError("Engine not initialised (async_session_factory is None).")
    session = factory()
    try:
        yield session
    finally:
        try:
            await session.close()
        except Exception:
            pass  # Suppress teardown errors on Windows ProactorEventLoop


# ── Tenant fixtures (used by C-02 tests) ──────────────────────────────


@pytest_asyncio.fixture
async def create_tenant(db_session):
    """Factory fixture that creates a Tenant and returns its ORM model.

    Usage::

        tenant = await create_tenant("tupad", "TUPAD")
    """
    from app.models.tenant import Tenant  # noqa: PLC0415

    async def _maker(codigo: str, nombre: str) -> Tenant:
        from sqlalchemy import text  # noqa: PLC0415
        result = await db_session.execute(
            text(
                "INSERT INTO tenant (codigo, nombre) "
                "VALUES (:c, :n) RETURNING id, codigo, nombre, estado, "
                "created_at, updated_at, deleted_at"
            ),
            {"c": codigo, "n": nombre},
        )
        await db_session.commit()
        row = result.one()
        return Tenant(
            id=row.id,
            codigo=row.codigo,
            nombre=row.nombre,
            estado=row.estado,
            created_at=row.created_at,
            updated_at=row.updated_at,
            deleted_at=row.deleted_at,
        )

    return _maker


@pytest_asyncio.fixture
async def another_tenant(db_session) -> str:
    """Fixture that creates a second tenant and returns its id as a string."""
    from sqlalchemy import text  # noqa: PLC0415
    codigo = f"another-{uuid.uuid4().hex[:6]}"
    result = await db_session.execute(
        text(
            "INSERT INTO tenant (codigo, nombre) "
            "VALUES (:c, :n) RETURNING id"
        ),
        {"c": codigo, "n": "Another Tenant"},
    )
    await db_session.commit()
    return str(result.scalar_one())


# ── FastAPI fixtures (used by test_health, test_app_startup) ────────


@pytest_asyncio.fixture
async def app() -> AsyncGenerator:
    """Provide the FastAPI application instance."""
    # Lazy-import to break circular dependency at module level.
    from app.main import create_app  # noqa: PLC0415

    application = create_app()
    yield application


@pytest_asyncio.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client wired to the test app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
