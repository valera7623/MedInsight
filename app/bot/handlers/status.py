""" /status — subscription and link status."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.models import EVENT_LABELS
from app.bot.services.user_service import TelegramUserService
from app.database import SessionLocal

router = Router(name="status")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not message.from_user:
        return
    db = SessionLocal()
    try:
        svc = TelegramUserService(db)
        row = svc.get_by_telegram_id(message.from_user.id)
        if not row or not row.is_active:
            await message.answer(
                "❌ Аккаунт <b>не привязан</b>.\n"
                "Отправьте /start, получите код и введите его в настройках MedInsight."
            )
            return

        user = svc.get_medinsight_user(message.from_user.id)
        subs = svc.get_subscriptions(message.from_user.id)
        if subs:
            sub_lines = "\n".join(f"• {EVENT_LABELS.get(e, e)}" for e in subs)
            subs_text = f"🔔 <b>Активные подписки:</b>\n{sub_lines}"
        else:
            subs_text = "🔕 Подписки отключены (/subscribe — включить)"

        email = user.email if user else "—"
        await message.answer(
            "✅ <b>Аккаунт привязан</b>\n"
            f"MedInsight: {email}\n\n"
            f"{subs_text}"
        )
    finally:
        db.close()
