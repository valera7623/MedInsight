"""Extract structured error signatures for RAG search."""

from __future__ import annotations

import re
import traceback
from typing import Any

KEYWORD_STOP = frozenset(
    {
        "the", "a", "an", "is", "was", "in", "at", "to", "for", "of",
        "and", "or", "not", "error", "exception", "failed", "line", "file",
    }
)

NON_HEALABLE_PATTERNS = (
    "api key",
    "authentication",
    "401",
    "403 forbidden",
    "invalid api key",
    "quota exceeded",
    "insufficient_quota",
    "permission denied",
)


def is_healable_error(error_text: str) -> bool:
    """Return False for errors that need manual intervention (auth/quota)."""
    lower = error_text.lower()
    return not any(pattern in lower for pattern in NON_HEALABLE_PATTERNS)


def _extract_keywords(message: str, limit: int = 10) -> list[str]:
    tokens = re.findall(r"[a-zA-Zа-яА-Я_][a-zA-Zа-яА-Я0-9_]*|\d+", message.lower())
    keywords: list[str] = []
    for token in tokens:
        if token in KEYWORD_STOP or len(token) < 2:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def _function_from_traceback(traceback_str: str) -> str | None:
    for line in reversed(traceback_str.splitlines()):
        match = re.search(r'File "[^"]+", line \d+, in (\w+)', line)
        if match:
            return match.group(1)
    return None


def extract_error_signature(
    exception: Exception,
    traceback_str: str,
    *,
    input_size: int | None = None,
) -> dict[str, Any]:
    """Build a structured error signature for indexing and search."""
    error_class = type(exception).__name__
    message = str(exception)
    module = type(exception).__module__
    full_type = f"{module}.{error_class}" if module and module != "builtins" else error_class

    if "ParserError" in error_class:
        full_type = "parser.ParserError"
    if "RateLimitError" in error_class:
        full_type = "openai.RateLimitError"
    if "UnicodeDecodeError" in error_class:
        full_type = "UnicodeDecodeError"

    return {
        "error_type": full_type,
        "error_class": error_class,
        "message": message[:500],
        "keywords": _extract_keywords(message),
        "function_name": _function_from_traceback(traceback_str),
        "input_size": input_size,
    }


def build_search_text(signature: dict[str, Any], stack_trace: str = "") -> str:
    """Combine signature fields into a single string for embedding/search."""
    parts = [
        signature.get("error_type", ""),
        signature.get("error_class", ""),
        signature.get("message", ""),
        " ".join(signature.get("keywords") or []),
        signature.get("function_name") or "",
        stack_trace[:300],
    ]
    return " ".join(p for p in parts if p).strip()


def format_traceback(exception: Exception) -> str:
    """Return traceback string capped at 1000 characters."""
    tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    return tb[:1000]
