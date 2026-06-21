"""Telegram bot entry point (aiogram polling or webhook)."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import setup_routers
from app.bot.middleware.rate_limit import BotRateLimitMiddleware
from app.config import settings
from app.database import Base, bootstrap_system, engine, run_migrations
from app.utils.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


async def _run_polling(bot: Bot, dp: Dispatcher) -> None:
    logger.info("Telegram bot starting (polling mode)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def _run_webhook(bot: Bot, dp: Dispatcher) -> None:
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    webhook_url = settings.TELEGRAM_BOT_WEBHOOK_URL.rstrip("/")
    secret = settings.TELEGRAM_BOT_WEBHOOK_SECRET or None
    logger.info("Telegram bot starting (webhook mode): %s", webhook_url)
    await bot.set_webhook(webhook_url, secret_token=secret, drop_pending_updates=True)

    app = web.Application()
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret)
    handler.register(app, path="/telegram/webhook")
    setup_application(app, dp, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=8081)
    await site.start()
    await asyncio.Event().wait()


async def main() -> None:
    if not settings.TELEGRAM_BOT_ENABLED:
        logger.info("TELEGRAM_BOT_ENABLED=false — bot process exiting")
        return
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set — bot cannot start")
        sys.exit(1)

    Base.metadata.create_all(bind=engine)
    run_migrations()
    bootstrap_system()

    bot = Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.message.middleware(BotRateLimitMiddleware())
    dp.callback_query.middleware(BotRateLimitMiddleware())
    dp.include_router(setup_routers())

    try:
        if settings.TELEGRAM_BOT_WEBHOOK_URL:
            await _run_webhook(bot, dp)
        else:
            await _run_polling(bot, dp)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Telegram bot stopped")
