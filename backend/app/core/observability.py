"""OpenTelemetry initialisation for FastAPI.

Provides ``setup_observability()`` which instruments the FastAPI
application with OpenTelemetry tracing. The instrumentation is
configurable via environment variables and does **not** block the
application start if no OTLP exporter backend is available.
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

# Environment variable that controls OTel export endpoint.
_OTEL_EXPORTER_OTLP_ENDPOINT = "OTEL_EXPORTER_OTLP_ENDPOINT"


def setup_observability(app_name: str = "activia-trace") -> None:
    """Instrument the application with OpenTelemetry.

    Creates a ``TracerProvider`` with a resource identifying the
    service and, if ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, attaches
    a batch span processor exporting to that endpoint.

    If no exporter endpoint is configured, spans are still created
    but simply dropped — the application continues to work normally
    (non-blocking observability).

    Args:
        app_name: The service name for the OTel resource.
    """
    resource = Resource.create({
        "service.name": app_name,
    })

    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.environ.get(_OTEL_EXPORTER_OTLP_ENDPOINT)
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)
            logger.info("OTLP exporter configured at %s", otlp_endpoint)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to configure OTLP exporter at %s: %s. "
                "Tracing will continue without export.",
                otlp_endpoint,
                exc,
            )
    else:
        logger.info(
            "No %s set — spans will be created but not exported. "
            "Set the env var to enable remote export.",
            _OTEL_EXPORTER_OTLP_ENDPOINT,
        )

    trace.set_tracer_provider(provider)


def instrument_fastapi(app: object) -> None:
    """Apply FastAPI auto-instrumentation.

    Must be called **after** ``setup_observability()`` and **after**
    all routes have been registered.

    Args:
        app: The FastAPI application instance.
    """
    FastAPIInstrumentor.instrument_app(app)
