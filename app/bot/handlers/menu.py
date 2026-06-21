""" /menu — main menu and quick subscription actions."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.main_menu import main_menu_keyboard
from app.bot.models import (
    CB_MAIN,
    EVENT_ANALYSIS_COMPLETED,
    EVENT_PREDICTION_READY,
)
from app.bot.services.user_service import TelegramUserService
from app.database import SessionLocal

router = Router(name="menu")

ABOUT_TEXT = (
    "ℹ️ <b>MedInsight Bot</b>\n\n"
    "Уведомления о событиях платформы MedInsight:\n"
    "• готовность прогнозов риска\n"
    "• завершение анализа документов\n"
    "• превышение лимитов\n"
    "• новые пациенты\n\n"
    "Команды: /settings, /status, /help"
)


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer("📋 <b>Главное меню</b>", reply_markup=main_menu_keyboard)


@router.callback_query(F.data.startswith(CB_MAIN))
async def on_main_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.data:
        return

    action = callback.data[len(CB_MAIN):]
    db = SessionLocal()
    try:
        svc = TelegramUserService(db)
        row = svc.get_by_telegram_id(callback.from_user.id)
        if not row or not row.is_active:
            await callback.answer("Сначала привяжите аккаунт через /start", show_alert=True)
            return

        if action == "predictions":
            subs = svc.get_subscriptions(callback.from_user.id)
            if EVENT_PREDICTION_READY in subs:
                subs = [e for e in subs if e != EVENT_PREDICTION_READY]
                svc.update_subscriptions(callback.from_user.id, subs)
                await callback.message.edit_text(  # type: ignore[union-attr]
                    "📊 Уведомления о <b>прогнозах</b> отключены.",
                    reply_markup=main_menu_keyboard,
                )
            else:
                subs = sorted(set(subs + [EVENT_PREDICTION_READY]))
                svc.update_subscriptions(callback.from_user.id, subs)
                await callback.message.edit_text(  # type: ignore[union-attr]
                    "📊 Уведомления о <b>прогнозах</b> включены.",
                    reply_markup=main_menu_keyboard,
                )
        elif action == "analysis":
            subs = svc.get_subscriptions(callback.from_user.id)
            if EVENT_ANALYSIS_COMPLETED in subs:
                subs = [e for e in subs if e != EVENT_ANALYSIS_COMPLETED]
                svc.update_subscriptions(callback.from_user.id, subs)
                await callback.message.edit_text(  # type: ignore[union-attr]
                    "📄 Уведомления об <b>анализах</b> отключены.",
                    reply_markup=main_menu_keyboard,
                )
            else:
                subs = sorted(set(subs + [EVENT_ANALYSIS_COMPLETED]))
                svc.update_subscriptions(callback.from_user.id, subs)
                await callback.message.edit_text(  # type: ignore[union-attr]
                    "📄 Уведомления об <b>анализах</b> включены.",
                    reply_markup=main_menu_keyboard,
                )
        elif action == "all_on":
            svc.subscribe_all(callback.from_user.id)
            await callback.message.edit_text(  # type: ignore[union-attr]
                "🔔 Все типы уведомлений <b>включены</b>.",
                reply_markup=main_menu_keyboard,
            )
        elif action == "all_off":
            svc.unsubscribe_all(callback.from_user.id)
            await callback.message.edit_text(  # type: ignore[union-attr]
                "🔕 Все уведомления <b>отключены</b>.",
                reply_markup=main_menu_keyboard,
            )
        elif action == "about":
            await callback.message.edit_text(ABOUT_TEXT, reply_markup=main_menu_keyboard)  # type: ignore[union-attr]
        await callback.answer()
    finally:
        db.close()
