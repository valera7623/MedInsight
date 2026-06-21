"""Redis-backed rate limiting for Telegram bot commands."""

from __future__ import annotations

import logging
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def check_telegram_rate_limit(telegram_user_id: int) -> tuple[bool, int]:
    """Rolling-window limit per Telegram user. Fail-open if Redis is down."""
    if not settings.TELEGRAM_BOT_ENABLED:
        return True, 0

    limit = settings.TELEGRAM_BOT_COMMAND_RATE_LIMIT
    period = 60
    client = get_redis()
    if client is None:
        return True, 0

    key = f"telegram_bot_rate:{telegram_user_id}"
    now = time.time()
    window_start = now - period

    try:
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {f"{now}": now})
        pipe.zcard(key)
        pipe.expire(key, period)
        results = pipe.execute()
        count = int(results[2])
        if count > limit:
            retry_after = max(1, int(period - (now - window_start)))
            return False, retry_after
        return True, 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("Telegram rate limit check failed: %s", exc)
        return True, 0


class BotRateLimitMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        if user is not None:
            allowed, retry_after = check_telegram_rate_limit(user.id)
            if not allowed:
                text = f"⏳ Слишком много запросов. Подождите {retry_after} сек."
                if isinstance(event, Message):
                    await event.answer(text)
                elif isinstance(event, CallbackQuery):
                    await event.answer(text, show_alert=True)
                return None

        return await handler(event, data)
