""" /settings — per-event notification toggles."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.settings_menu import settings_menu_keyboard
from app.bot.models import CB_SETTINGS, CB_TOGGLE, EVENT_LABELS
from app.bot.services.user_service import TelegramUserService
from app.database import SessionLocal

router = Router(name="settings")


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    if not message.from_user:
        return
    db = SessionLocal()
    try:
        svc = TelegramUserService(db)
        row = svc.get_by_telegram_id(message.from_user.id)
        if not row or not row.is_active:
            await message.answer("⚠️ Сначала привяжите аккаунт через /start")
            return
        subs = svc.get_subscriptions(message.from_user.id)
        await message.answer(
            "⚙️ <b>Настройки уведомлений</b>\nНажмите, чтобы включить или выключить:",
            reply_markup=settings_menu_keyboard(subs),
        )
    finally:
        db.close()


@router.callback_query(F.data.startswith(CB_TOGGLE))
async def toggle_event(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return
    event = callback.data[len(CB_TOGGLE):]
    db = SessionLocal()
    try:
        svc = TelegramUserService(db)
        row = svc.get_by_telegram_id(callback.from_user.id)
        if not row or not row.is_active:
            await callback.answer("Привяжите аккаунт через /start", show_alert=True)
            return
        subs = svc.toggle_subscription(callback.from_user.id, event)
        label = EVENT_LABELS.get(event, event)
        enabled = event in subs
        await callback.message.edit_text(  # type: ignore[union-attr]
            f"⚙️ <b>Настройки уведомлений</b>\n{label}: {'включено' if enabled else 'выключено'}",
            reply_markup=settings_menu_keyboard(subs),
        )
        await callback.answer()
    finally:
        db.close()


@router.callback_query(F.data == f"{CB_SETTINGS}back")
async def settings_back(callback: CallbackQuery) -> None:
    from app.bot.keyboards.main_menu import main_menu_keyboard

    if callback.message:
        await callback.message.edit_text("📋 <b>Главное меню</b>", reply_markup=main_menu_keyboard)
    await callback.answer()
