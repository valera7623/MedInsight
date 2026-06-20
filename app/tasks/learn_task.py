"""Periodic self-healing learning task (Celery Beat, every 6h)."""

from __future__ import annotations

import asyncio
import json
import logging

from app.config import settings
from app.services.openai_client import chat_completion_json
from app.services.self_healing.vector_store import get_knowledge_base, is_self_healing_enabled, seed_knowledge_base
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _suggest_fix(record: dict) -> dict:
    prompt = (
        "Вот повторяющаяся ошибка в медицинском пайплайне и неудачные попытки её исправить. "
        "Предложи безопасное техническое решение (без изменения бизнес-логики).\n\n"
        f"Agent: {record.get('agent_name')}\n"
        f"Error: {record.get('error_text', '')[:800]}\n"
        f"Предыдущий prompt: {record.get('solution_prompt', '')}\n\n"
        'Верни JSON: {"solution_prompt": "...", '
        '"solution_code": {"action": "retry_exponential_backoff|context_overlay|retry_simple", "params": {}}}'
    )
    return await chat_completion_json(
        messages=[
            {
                "role": "system",
                "content": "Ты DevOps-инженер. Предлагаешь безопасные retry-фиксы. Только JSON, без выполнения кода.",
            },
            {"role": "user", "content": prompt},
        ]
    )


@celery_app.task(name="app.tasks.learn_task.learn_from_failures")
def learn_from_failures() -> dict:
    """Analyze stale failed fixes and generate LLM candidate solutions."""
    if not is_self_healing_enabled():
        return {"status": "skipped", "reason": "self_healing_disabled"}

    kb = get_knowledge_base()
    if kb is None:
        return {"status": "skipped", "reason": "kb_unavailable"}

    # Ensure seed fixes exist on first run.
    seed_knowledge_base()

    if not settings.OPENAI_API_KEY:
        logger.info("learn_from_failures: OPENAI_API_KEY not set — skipping LLM generation")
        return {"status": "skipped", "reason": "no_openai_key"}

    stale = kb.find_stale_failures(min_age_days=7)
    generated = 0
    for record in stale[:10]:
        try:
            suggestion = asyncio.run(_suggest_fix(record))
            solution_code = suggestion.get("solution_code")
            if isinstance(solution_code, str):
                try:
                    solution_code = json.loads(solution_code)
                except json.JSONDecodeError:
                    solution_code = None
            kb.add_error(
                {
                    "error_text": record.get("error_text", ""),
                    "error_type": record.get("error_type", "unknown"),
                    "agent_name": record.get("agent_name", "unknown"),
                    "stack_trace": record.get("stack_trace", ""),
                    "solution_prompt": suggestion.get("solution_prompt", ""),
                    "solution_code": solution_code,
                    "was_successful": False,
                    "success_count": 0,
                    "fail_count": 0,
                    "tenant_id": record.get("tenant_id"),
                }
            )
            generated += 1
        except Exception as exc:
            logger.warning("learn_from_failures failed for fix %s: %s", record.get("id"), exc)

    logger.info("learn_from_failures: %d stale, %d candidates generated", len(stale), generated)
    return {"status": "ok", "stale_count": len(stale), "generated": generated}
