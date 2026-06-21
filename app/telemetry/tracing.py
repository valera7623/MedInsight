"""Custom span helpers — re-exported from :mod:`app.utils.tracing`.

Kept as a thin shim so callers can import from either ``app.telemetry.tracing``
or ``app.utils.tracing``.
"""

from app.utils.tracing import (  # noqa: F401
    add_span_attributes,
    get_tracer,
    trace_span,
    tracing_active,
)

__all__ = ["trace_span", "add_span_attributes", "get_tracer", "tracing_active"]
