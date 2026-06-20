"""Worker de despacho de comunicaciones — C-12 comunicaciones-cola-worker.

Loop asyncio que despacha las Comunicaciones en estado ENVIANDO.

Tecnología (ADR-003): polling asyncio in-process sin broker externo.
Swappable: el dispatcher se inyecta → FakeSender en dev/tests, SmtpSender en prod.

Invariante PII: el email del destinatario (com.destinatario) se descifra
automáticamente por EncryptedString al leer el ORM, pero NUNCA se loguea.
Solo se registran com.id y el estado resultado.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


async def dispatch_loop(dispatcher, session_factory, poll_interval: int = 5) -> None:
    """Loop principal del worker.

    Args:
        dispatcher: implementación de AbstractEmailDispatcher.
        session_factory: callable async que produce AsyncSession.
        poll_interval: segundos entre iteraciones.
    """
    from app.models.comunicacion import EstadoComunicacion  # noqa: PLC0415
    from app.repositories.comunicacion_repository import ComunicacionRepository  # noqa: PLC0415

    logger.info("Worker dispatch loop started (poll_interval=%ds)", poll_interval)

    while True:
        try:
            async with session_factory() as session:
                pendientes = await ComunicacionRepository.list_enviando_all_tenants(
                    session, limit=100
                )
                if pendientes:
                    logger.info("Worker: dispatching %d messages", len(pendientes))

                for com in pendientes:
                    try:
                        # EncryptedString descifra automáticamente — NO loguear email
                        email = com.destinatario
                        ok = await dispatcher.send(email, com.asunto, com.cuerpo)
                        nuevo = (
                            EstadoComunicacion.ENVIADO if ok else EstadoComunicacion.ERROR
                        )
                    except Exception as exc:
                        logger.error("Dispatch failed for com.id=%s: %s", com.id, exc)
                        nuevo = EstadoComunicacion.ERROR

                    await ComunicacionRepository.set_estado_worker(
                        session,
                        com,
                        nuevo,
                        enviado_at=datetime.now(tz=timezone.utc) if nuevo == EstadoComunicacion.ENVIADO else None,
                    )
                    logger.info("com.id=%s → %s", com.id, nuevo.value)
                    await session.commit()

        except asyncio.CancelledError:
            logger.info("Worker dispatch loop cancelled.")
            raise
        except Exception as exc:
            logger.error("Worker loop iteration failed: %s", exc)

        await asyncio.sleep(poll_interval)


async def main() -> None:
    """Entrypoint del worker — construye el dispatcher y arranca el loop."""
    setup_logging()
    logger.info("Worker starting.")

    from app.core.config import settings  # noqa: PLC0415
    from app.core.database import async_session_factory  # noqa: PLC0415
    from app.integrations.email_dispatcher import build_dispatcher_from_settings  # noqa: PLC0415

    dispatcher = build_dispatcher_from_settings()
    logger.info("Email backend: %s", settings.EMAIL_BACKEND)

    # async_session_factory es un sessionmaker; lo envolvemos en context manager
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: PLC0415
    from contextlib import asynccontextmanager  # noqa: PLC0415

    @asynccontextmanager
    async def session_ctx():
        session: AsyncSession = async_session_factory()
        try:
            yield session
        finally:
            await session.close()

    stop_event = asyncio.Event()
    loop_task = asyncio.create_task(
        dispatch_loop(dispatcher, session_ctx, poll_interval=settings.WORKER_POLL_INTERVAL_SECS)
    )
    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass
        logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
