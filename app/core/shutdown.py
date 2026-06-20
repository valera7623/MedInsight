"""Ordered, fault-tolerant shutdown orchestration.

``ShutdownManager`` collects named cleanup handlers and runs them sequentially
during graceful shutdown. Each handler is given an individual timeout and any
failure is logged but never aborts the remaining handlers, so one stuck resource
cannot leak the others.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

HandlerCallback = Callable[[], Any] | Callable[[], Awaitable[Any]]


@dataclass
class _Handler:
    name: str
    callback: HandlerCallback
    timeout: float


class ShutdownManager:
    """Registers cleanup callbacks and runs them in order on shutdown."""

    def __init__(self) -> None:
        self._handlers: list[_Handler] = []
        self._completed = False

    def register_handler(self, name: str, callback: HandlerCallback, timeout: float = 5) -> None:
        """Register a cleanup ``callback`` (sync or async) executed on shutdown."""
        self._handlers.append(_Handler(name=name, callback=callback, timeout=timeout))
        logger.debug("Shutdown handler registered: %s (timeout=%ss)", name, timeout)

    async def _run_one(self, handler: _Handler) -> None:
        started = time.monotonic()
        logger.info("[shutdown] -> %s (timeout=%ss)", handler.name, handler.timeout)
        try:
            result = handler.callback()
            if inspect.isawaitable(result):
                await asyncio.wait_for(result, timeout=handler.timeout)
            else:
                # Run blocking sync callbacks off the event loop with a timeout.
                await asyncio.wait_for(
                    asyncio.to_thread(lambda: result), timeout=handler.timeout
                )
            elapsed = (time.monotonic() - started) * 1000
            logger.info("[shutdown] OK  %s (%.0fms)", handler.name, elapsed)
        except asyncio.TimeoutError:
            logger.error("[shutdown] TIMEOUT %s after %ss", handler.name, handler.timeout)
        except Exception as exc:  # noqa: BLE001 — keep tearing down remaining resources
            logger.error("[shutdown] FAIL %s: %s", handler.name, exc)

    async def shutdown(self) -> None:
        """Run every registered handler once, in registration order."""
        if self._completed:
            return
        self._completed = True
        logger.info("[shutdown] Starting graceful shutdown (%d handlers)", len(self._handlers))
        # Shield the whole sequence so an outer cancellation doesn't interrupt cleanup.
        await asyncio.shield(self._run_all())
        logger.info("[shutdown] Graceful shutdown complete")

    async def _run_all(self) -> None:
        for handler in self._handlers:
            await self._run_one(handler)


shutdown_manager = ShutdownManager()
