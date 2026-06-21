"""``@trace_span`` decorator + tracer helpers.

Fully optional: if ``opentelemetry`` isn't installed or ``OTEL_ENABLED`` is off,
the decorator is a transparent pass-through (zero overhead, no errors). When
tracing is active it creates a child span, attaches attributes, records
exceptions, and adds a ``duration_ms`` attribute.
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

from app.config import settings

try:
    from opentelemetry import trace as _otel_trace

    _OTEL_AVAILABLE = True
except Exception:  # noqa: BLE001
    _OTEL_AVAILABLE = False


def tracing_active() -> bool:
    return bool(settings.OTEL_ENABLED and _OTEL_AVAILABLE)


def get_tracer(name: str = "medinsight"):
    if not tracing_active():
        return None
    return _otel_trace.get_tracer(name)


def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Callable:
    """Wrap a sync or async callable in an OTel child span (when enabled)."""

    def decorator(func: Callable) -> Callable:
        is_async = _is_coroutine(func)

        if is_async:

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                tracer = get_tracer()
                if tracer is None:
                    return await func(*args, **kwargs)
                with tracer.start_as_current_span(name) as span:
                    _set_attrs(span, attributes)
                    start = time.perf_counter()
                    try:
                        return await func(*args, **kwargs)
                    except Exception as exc:  # noqa: BLE001
                        _record_error(span, exc)
                        raise
                    finally:
                        _set_duration(span, start)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            tracer = get_tracer()
            if tracer is None:
                return func(*args, **kwargs)
            with tracer.start_as_current_span(name) as span:
                _set_attrs(span, attributes)
                start = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    _record_error(span, exc)
                    raise
                finally:
                    _set_duration(span, start)

        return sync_wrapper

    return decorator


def add_span_attributes(**attributes: Any) -> None:
    """Attach attributes to the current active span (no-op when disabled)."""
    if not tracing_active():
        return
    span = _otel_trace.get_current_span()
    if span is not None:
        _set_attrs(span, attributes)


def _set_attrs(span, attributes: dict[str, Any] | None) -> None:
    if not attributes:
        return
    for key, value in attributes.items():
        if value is not None:
            try:
                span.set_attribute(key, value)
            except Exception:  # noqa: BLE001
                span.set_attribute(key, str(value))


def _set_duration(span, start: float) -> None:
    try:
        span.set_attribute("duration_ms", round((time.perf_counter() - start) * 1000, 2))
    except Exception:  # noqa: BLE001
        pass


def _record_error(span, exc: Exception) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode

        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:  # noqa: BLE001
        pass


def _is_coroutine(func: Callable) -> bool:
    import asyncio

    return asyncio.iscoroutinefunction(func)
