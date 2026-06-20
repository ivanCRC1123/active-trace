"""Email dispatcher abstraction — C-12 comunicaciones-cola-worker.

Provides a swappable email sender (patrón idéntico a moodle_ws.py):
  - AbstractEmailDispatcher: Protocol (duck-typing interface)
  - FakeSender: dev/tests — in-process, no network, captures sent messages
  - SmtpSender: production — real SMTP via aiosmtplib (instalado en pyproject.toml)

El worker inyecta la implementación según settings.EMAIL_BACKEND.
En tests se inyecta FakeSender directamente, sin leer settings.
"""
from __future__ import annotations

import asyncio
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class EmailDispatchError(Exception):
    """Raised when the dispatcher fails to send a message."""


@runtime_checkable
class AbstractEmailDispatcher(Protocol):
    async def send(self, to: str, subject: str, body: str) -> bool:
        """Send an email.

        Returns True on success, False on a non-fatal failure.
        Raises EmailDispatchError on fatal errors.
        Note: `to` is ALREADY decrypted — do not log it.
        """
        ...


class FakeSender:
    """In-process dispatcher for dev/tests.

    No network calls. Every sent message is appended to self.sent.
    fail_next can be set to True to simulate a dispatch failure once.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail_next: bool = False

    async def send(self, to: str, subject: str, body: str) -> bool:
        if self.fail_next:
            self.fail_next = False
            return False
        # Never log `to` — it contains PII (email del alumno)
        logger.debug("FakeSender: message enqueued (recipient suppressed)")
        self.sent.append({"subject": subject, "body": body})
        return True

    def reset(self) -> None:
        self.sent.clear()
        self.fail_next = False


class SmtpSender:
    """Production SMTP dispatcher using aiosmtplib.

    Reads config from app.core.config.settings at instantiation time.
    The `from_email` address is configurable via SMTP_FROM_EMAIL.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_email = from_email
        self._use_tls = use_tls

    async def send(self, to: str, subject: str, body: str) -> bool:
        try:
            import aiosmtplib  # noqa: PLC0415
        except ImportError as exc:
            raise EmailDispatchError(
                "aiosmtplib not installed — add it to pyproject.toml for SMTP support"
            ) from exc

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from_email
        msg["To"] = to
        msg.attach(MIMEText(body, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._host,
                port=self._port,
                username=self._user,
                password=self._password,
                use_tls=self._use_tls,
            )
            # Do NOT log `to`
            logger.info("Email dispatched successfully")
            return True
        except Exception as exc:
            logger.error("SMTP send failed: %s", exc)
            return False


def build_dispatcher_from_settings() -> AbstractEmailDispatcher:
    """Factory: construye el dispatcher correcto según settings.EMAIL_BACKEND."""
    from app.core.config import settings  # noqa: PLC0415

    backend = settings.EMAIL_BACKEND.lower()
    if backend == "smtp":
        return SmtpSender(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            user=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            from_email=settings.SMTP_FROM_EMAIL,
            use_tls=settings.SMTP_USE_TLS,
        )
    return FakeSender()
