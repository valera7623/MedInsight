""" /unsubscribe — disable all notification types."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.services.user_service import TelegramUserService
from app.database import SessionLocal

router = Router(name="unsubscribe")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message) -> None:
    if not message.from_user:
        return
    db = SessionLocal()
    try:
        svc = TelegramUserService(db)
        row = svc.get_by_telegram_id(message.from_user.id)
        if not row or not row.is_active:
            await message.answer("⚠️ Сначала привяжите аккаунт через /start")
            return
        svc.unsubscribe_all(message.from_user.id)
        await message.answer("🔕 Все уведомления отключены. /subscribe — включить снова.")
    finally:
        db.close()
