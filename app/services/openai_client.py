import json
import logging
from functools import lru_cache
from typing import Any

from openai import APIStatusError, AsyncOpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.utils.tracing import add_span_attributes, get_tracer

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenAIClientError(Exception):
    """Raised when OpenAI/ProxyAPI request fails after retries."""


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI | None:
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not configured — GPT features will use rule-based fallback")
        return None
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=60.0,
    )


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUS_CODES
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
async def chat_completion_json(
    messages: list[dict[str, str]],
    model: str | None = None,
) -> dict[str, Any]:
    client = get_openai_client()
    if client is None:
        raise OpenAIClientError("OpenAI client not configured")

    model_name = model or settings.OPENAI_MODEL

    tracer = get_tracer("medinsight.openai")
    span_cm = tracer.start_as_current_span("openai_call") if tracer is not None else None
    if span_cm is not None:
        span_cm.__enter__()
        add_span_attributes(model=model_name)

    try:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except APIStatusError as exc:
            if exc.status_code in (401, 404):
                logger.error("ProxyAPI auth/routing error (HTTP %s)", exc.status_code)
            elif exc.status_code == 429:
                logger.warning("ProxyAPI rate limit (HTTP 429), retrying...")
            elif exc.status_code >= 500:
                logger.warning("ProxyAPI server error (HTTP %s), retrying...", exc.status_code)
            if not _is_retryable(exc):
                raise OpenAIClientError(f"ProxyAPI error: HTTP {exc.status_code}") from exc
            raise

        usage = getattr(response, "usage", None)
        if usage is not None:
            add_span_attributes(
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )

        content = response.choices[0].message.content
        if not content:
            raise OpenAIClientError("Empty response from GPT")

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAIClientError("Invalid JSON in GPT response") from exc
    finally:
        if span_cm is not None:
            span_cm.__exit__(None, None, None)
