"""Self-healing decorator for agent functions."""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

from app.config import settings
from app.services.self_healing.error_analyzer import (
    build_search_text,
    extract_error_signature,
    format_traceback,
)
from app.services.self_healing.fix_executor import FixExecutor
from app.services.self_healing.vector_store import get_knowledge_base, is_self_healing_enabled

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _extract_context(agent_name: str, args: tuple, kwargs: dict) -> dict[str, Any]:
    ctx: dict[str, Any] = {"agent_name": agent_name}
    for key in ("patient_id", "document_id", "job_id", "tenant_id"):
        if key in kwargs:
            ctx[key] = kwargs[key]
    return ctx


def with_self_healing(agent_name: str, max_retries: int | None = None) -> Callable[[F], F]:
    """Decorator: on exception, search the knowledge base for similar fixes and retry.

    Falls through transparently when self-healing is disabled or the knowledge
    base is unavailable, so wrapped agents behave exactly as before.
    """
    fix_attempts = max_retries if max_retries is not None else settings.MAX_RETRY_ATTEMPTS

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not is_self_healing_enabled():
                return func(*args, **kwargs)

            kb = get_knowledge_base()
            if kb is None:
                return func(*args, **kwargs)

            try:
                return func(*args, **kwargs)
            except Exception as exc:
                context = _extract_context(agent_name, args, kwargs)
                tb_str = format_traceback(exc)
                signature = extract_error_signature(exc, tb_str)
                search_text = build_search_text(signature, tb_str)

                logger.warning(
                    "Agent %s failed — self-healing: %s",
                    agent_name, signature.get("message", "")[:120],
                )

                similar = kb.search_similar_errors(
                    search_text, agent_name=agent_name, limit=3,
                    threshold=settings.SIMILARITY_THRESHOLD,
                )
                viable = [
                    f for f in similar
                    if f.get("was_successful") and f.get("success_count", 0) > f.get("fail_count", 0)
                ]

                executor = FixExecutor(agent_name)
                for attempt in range(1, fix_attempts + 1):
                    if not viable:
                        break
                    success, result, fix_id_used = executor.attempt_fix(
                        exc, context, viable, retry_fn=lambda: func(*args, **kwargs)
                    )
                    if success and result is not None:
                        if fix_id_used is not None:
                            kb.mark_fix_success(fix_id_used)
                        logger.info(
                            "Self-healing succeeded for %s on attempt %d (fix_id=%s)",
                            agent_name, attempt, fix_id_used,
                        )
                        return result
                    for fix in viable:
                        if fix.get("id") is not None:
                            kb.mark_fix_failure(fix["id"])

                # Nothing worked — record the new failure for future learning.
                try:
                    kb.add_error(
                        {
                            "error_text": search_text,
                            "error_type": signature.get("error_type", agent_name),
                            "agent_name": agent_name,
                            "stack_trace": tb_str,
                            "solution_prompt": "",
                            "solution_code": None,
                            "was_successful": False,
                            "success_count": 0,
                            "fail_count": 1,
                            "tenant_id": context.get("tenant_id"),
                        }
                    )
                except Exception as store_exc:
                    logger.warning("Self-healing: could not store new error: %s", store_exc)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
