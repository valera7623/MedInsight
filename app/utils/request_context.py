"""Per-request context propagated via :mod:`contextvars`.

Values stored here flow automatically into structlog log lines (through
``structlog.contextvars.merge_contextvars``) and survive ``await`` boundaries,
so any code — including background coroutines spawned from a request — can read
the current ``request_id`` / ``user_id`` / ``tenant_id`` without threading them
through every function call.
"""

from __future__ import annotations

import contextvars
from typing import Any

import structlog

# Raw contextvars (source of truth). structlog also keeps its own contextvar
# bag; we mirror into it so the values appear in every log event.
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_user_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("user_id", default=None)
_tenant_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("tenant_id", default=None)
_ip_address: contextvars.ContextVar[str | None] = contextvars.ContextVar("ip_address", default=None)
_user_agent: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_agent", default=None)


def bind_request_context(
    *,
    request_id: str | None = None,
    user_id: int | None = None,
    tenant_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Set context values (only non-None ones) for the current execution context."""
    data: dict[str, Any] = {}
    if request_id is not None:
        _request_id.set(request_id)
        data["request_id"] = request_id
    if user_id is not None:
        _user_id.set(user_id)
        data["user_id"] = user_id
    if tenant_id is not None:
        _tenant_id.set(tenant_id)
        data["tenant_id"] = tenant_id
    if ip_address is not None:
        _ip_address.set(ip_address)
        data["ip"] = ip_address
    if user_agent is not None:
        _user_agent.set(user_agent)
        data["user_agent"] = user_agent
    if data:
        structlog.contextvars.bind_contextvars(**data)


def get_request_id() -> str | None:
    return _request_id.get()


def get_user_id() -> int | None:
    return _user_id.get()


def get_tenant_id() -> int | None:
    return _tenant_id.get()


def get_context() -> dict[str, Any]:
    """Snapshot of the current request context (only set values)."""
    out: dict[str, Any] = {}
    for key, var in (
        ("request_id", _request_id),
        ("user_id", _user_id),
        ("tenant_id", _tenant_id),
        ("ip", _ip_address),
        ("user_agent", _user_agent),
    ):
        value = var.get()
        if value is not None:
            out[key] = value
    return out


def clear_request_context() -> None:
    """Reset both the raw contextvars and structlog's contextvar bag."""
    _request_id.set(None)
    _user_id.set(None)
    _tenant_id.set(None)
    _ip_address.set(None)
    _user_agent.set(None)
    structlog.contextvars.clear_contextvars()
