"""Apply known fixes and validate results — declarative actions, no eval."""

from __future__ import annotations

import logging
import random
import time
from difflib import get_close_matches
from typing import Any, Callable

from app.services.self_healing.error_analyzer import is_healable_error

logger = logging.getLogger(__name__)

# Thread-local-ish overlay that wrapped agents may read during a retry.
_active_fix_context: dict[str, Any] = {}


def get_active_fix_context() -> dict[str, Any]:
    """Return the current fix overlay context (read by agents during retry)."""
    return dict(_active_fix_context)


def _apply_fuzzy(context: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    overlay = {**context, **params}
    missing = overlay.get("_missing_key")
    available = overlay.get("available_keys") or []
    if missing and available:
        matches = get_close_matches(str(missing), [str(c) for c in available], n=1, cutoff=0.6)
        if matches:
            overlay["_key_remap"] = {missing: matches[0]}
    return overlay


class FixExecutor:
    """Execute fix strategies and retry the wrapped agent call."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name

    def attempt_fix(
        self,
        error: Exception,
        context: dict[str, Any],
        similar_fixes: list[dict[str, Any]],
        retry_fn: Callable[[], Any],
    ) -> tuple[bool, Any, int | None]:
        """Try applying fixes from the knowledge base.

        Returns (success, result, fix_id_used).
        """
        if not is_healable_error(str(error)):
            logger.info("Self-healing: error not auto-healable for %s", self.agent_name)
            return False, None, None

        for fix in similar_fixes:
            fix_id = fix.get("id")
            if fix.get("was_successful") and fix.get("success_count", 0) <= fix.get("fail_count", 0):
                continue
            try:
                ok, result = self._apply_single(context, fix, retry_fn)
                if ok and result is not None:
                    return True, result, fix_id
            except Exception as exc:
                logger.warning("Self-healing: fix %s raised during retry: %s", fix_id, exc)
        return False, None, None

    def _apply_single(
        self, context: dict[str, Any], fix: dict[str, Any], retry_fn: Callable[[], Any]
    ) -> tuple[bool, Any]:
        global _active_fix_context
        spec = fix.get("solution_code") or {}
        if isinstance(spec, str):
            import json

            try:
                spec = json.loads(spec)
            except json.JSONDecodeError:
                spec = {}

        action = spec.get("action", "retry_simple")
        params = spec.get("params") or {}

        logger.info(
            "Self-healing: applying action=%s agent=%s fix_id=%s",
            action, self.agent_name, fix.get("id"),
        )

        _active_fix_context = {}
        try:
            if action == "retry_exponential_backoff":
                base = float(params.get("base_delay", 1.0))
                time.sleep(min(base + random.uniform(0, 0.5), 10.0))
                result = retry_fn()
            elif action == "fuzzy_column_match":
                _active_fix_context = _apply_fuzzy(context, params)
                result = retry_fn()
            elif action == "context_overlay":
                _active_fix_context = {**context, **params}
                result = retry_fn()
            else:  # retry_simple / unknown -> plain retry
                result = retry_fn()

            return self._validate(result), result
        finally:
            _active_fix_context = {}

    @staticmethod
    def _validate(result: Any) -> bool:
        if result is None:
            return False
        if isinstance(result, dict) and result.get("status") == "failed":
            return False
        return True
