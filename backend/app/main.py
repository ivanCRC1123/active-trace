"""FastAPI application bootstrap.

Creates and configures the FastAPI ``app`` instance with:
- Lifespan that sets up JSON structured logging and OpenTelemetry.
- Database engine is initialised at import time in ``core/database.py``.
- Registered API routers (``/health``).
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.routers import analisis, asignaciones, auth, auditoria, calificaciones, coloquios, comunicaciones, equipos, estructura_academica, health, padron, programas_y_fechas, usuarios
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup / shutdown logic.

    Startup:
        - Set up JSON structured logging.
        - Set up OpenTelemetry instrumentation.

    Shutdown:
        - (Engine disposal is handled by SQLAlchemy pool on interpreter
          exit for now; explicit dispose can be added later.)
    """
    # Startup
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Application starting — logging configured.")

    from app.core.observability import instrument_fastapi, setup_observability  # noqa: PLC0415
    setup_observability()
    instrument_fastapi(app)
    logger.info("OpenTelemetry instrumentation applied.")

    yield
    # Shutdown — reserved for future cleanup.


def create_app() -> FastAPI:
    """Build and return a fully configured FastAPI application.

    This factory allows creating independent instances for testing
    without module-level side effects.
    """
    app = FastAPI(
        title="activia-trace",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Register routers ─────────────────────────────────────────
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(auditoria.router)
    app.include_router(estructura_academica.router)
    app.include_router(usuarios.router)
    app.include_router(asignaciones.router)
    app.include_router(equipos.router)
    app.include_router(padron.router)
    app.include_router(calificaciones.router)
    app.include_router(analisis.router)
    app.include_router(comunicaciones.router)
    app.include_router(programas_y_fechas.router_programas)
    app.include_router(programas_y_fechas.router_fechas)
    app.include_router(coloquios.router)

    return app


# Module-level instance for ``uvicorn`` to import.
app = create_app()
