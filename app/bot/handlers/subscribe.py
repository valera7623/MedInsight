""" /subscribe — enable all notification types."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.models import EVENT_LABELS
from app.bot.services.user_service import TelegramUserService
from app.database import SessionLocal

router = Router(name="subscribe")


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    if not message.from_user:
        return
    db = SessionLocal()
    try:
        svc = TelegramUserService(db)
        row = svc.get_by_telegram_id(message.from_user.id)
        if not row or not row.is_active:
            await message.answer("⚠️ Сначала привяжите аккаунт через /start")
            return
        svc.subscribe_all(message.from_user.id)
        labels = ", ".join(EVENT_LABELS.values())
        await message.answer(f"🔔 Вы подписаны на все уведомления:\n{labels}")
    finally:
        db.close()
