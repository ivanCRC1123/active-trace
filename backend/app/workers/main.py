"""Worker entrypoint — placeholder.

La tecnología real de la cola de comunicaciones (asyncio propio /
Celery / ARQ) se definirá en ADR-003 al construir el módulo de
comunicaciones. Por ahora este archivo es un entrypoint mínimo
que puede ejecutarse como proceso separado en el contenedor
``worker`` del docker-compose.
"""

import asyncio
import logging

from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


async def main() -> None:
    """Worker main loop — placeholder.

    In a future change this will connect to a job queue, consume
    messages and dispatch them to the appropriate handlers.
    """
    setup_logging()
    logger.info("Worker started (placeholder — no jobs configured).")

    # Keep the process alive until interrupted.
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        logger.info("Worker shutting down.")


if __name__ == "__main__":
    asyncio.run(main())
