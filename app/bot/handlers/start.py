""" /start — greeting and account linking code generation."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.services.link_codes import generate_link_code
from app.bot.services.user_service import TelegramUserService
from app.config import settings
from app.database import SessionLocal

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return

    tg = message.from_user
    db = SessionLocal()
    try:
        svc = TelegramUserService(db)
        linked = svc.get_by_telegram_id(tg.id)
        if linked and linked.is_active:
            user = svc.get_medinsight_user(tg.id)
            name = user.full_name if user else "пользователь"
            await message.answer(
                f"👋 Снова здравствуйте, {name}!\n\n"
                "Ваш аккаунт MedInsight уже привязан.\n"
                "Используйте /menu для управления уведомлениями.",
                reply_markup=main_menu_keyboard,
            )
            return
    finally:
        db.close()

    code = generate_link_code(
        telegram_user_id=tg.id,
        telegram_username=tg.username,
        first_name=tg.first_name or "",
        last_name=tg.last_name,
    )
    if not code:
        await message.answer(
            "⚠️ Сервис временно недоступен (Redis). Попробуйте позже или обратитесь к администратору."
        )
        return

    site = (settings.FRONTEND_URL or "MedInsight").rstrip("/")
    await message.answer(
        "👋 <b>Добро пожаловать в MedInsight Bot!</b>\n\n"
        "Этот бот отправляет уведомления о прогнозах, анализах, лимитах и новых пациентах.\n\n"
        f"🔐 <b>Ваш код подтверждения:</b> <code>{code}</code>\n\n"
        f"1. Войдите на сайт: {site}\n"
        "2. Откройте настройки профиля → «Telegram»\n"
        "3. Введите код (действует 10 минут)\n\n"
        "После привязки используйте /menu для настройки уведомлений.",
        reply_markup=main_menu_keyboard,
    )
