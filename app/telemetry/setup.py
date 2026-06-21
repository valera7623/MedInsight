"""OpenTelemetry initialisation.

All setup is guarded: if the OTel packages aren't installed or ``OTEL_ENABLED``
is false, every function becomes a no-op so the app runs unchanged. Tracing
exports spans to an OTLP (gRPC) collector / Jaeger via ``BatchSpanProcessor``.
"""

from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

_initialised = False


def setup_telemetry() -> bool:
    """Configure the global TracerProvider + OTLP exporter. Idempotent."""
    global _initialised
    if _initialised:
        return True
    if not settings.OTEL_ENABLED:
        logger.info("OpenTelemetry disabled (OTEL_ENABLED=false)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenTelemetry packages not available (%s) — tracing disabled", exc)
        return False

    try:
        resource = Resource.create({
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.APP_VERSION,
            "deployment.environment": settings.OTEL_DEPLOYMENT_ENVIRONMENT,
        })
        sampler = ParentBasedTraceIdRatio(settings.OTEL_TRACES_SAMPLER_ARG)
        provider = TracerProvider(resource=resource, sampler=sampler)

        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        _set_w3c_propagator()
        _initialised = True
        logger.info(
            "OpenTelemetry initialised: service=%s endpoint=%s sample=%.2f",
            settings.OTEL_SERVICE_NAME, settings.OTEL_EXPORTER_OTLP_ENDPOINT, settings.OTEL_TRACES_SAMPLER_ARG,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenTelemetry setup failed (%s) — tracing disabled", exc)
        return False


def _set_w3c_propagator() -> None:
    try:
        from opentelemetry.propagate import set_global_textmap
        from opentelemetry.propagators.composite import CompositePropagator
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        from opentelemetry.baggage.propagation import W3CBaggagePropagator

        set_global_textmap(CompositePropagator([
            TraceContextTextMapPropagator(),
            W3CBaggagePropagator(),
        ]))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not set W3C propagator: %s", exc)


def instrument_all(app=None, engine=None) -> None:
    """Instrument FastAPI + libraries. Each step is independent and optional."""
    if not (settings.OTEL_ENABLED and _initialised):
        return
    from app.telemetry.db import instrument_db
    from app.telemetry.fastapi import instrument_fastapi
    from app.telemetry.redis import instrument_redis

    if app is not None:
        instrument_fastapi(app)
    instrument_db(engine)
    instrument_redis()
    _instrument_http()


def _instrument_http() -> None:
    for modpath, clsname in (
        ("opentelemetry.instrumentation.requests", "RequestsInstrumentor"),
        ("opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor"),
    ):
        try:
            module = __import__(modpath, fromlist=[clsname])
            getattr(module, clsname)().instrument()
            logger.info("OTel instrumented: %s", clsname)
        except Exception as exc:  # noqa: BLE001
            logger.debug("HTTP instrumentation (%s) skipped: %s", clsname, exc)
