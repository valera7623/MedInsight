"""Main menu inline keyboard."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.models import CB_MAIN

main_menu_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📊 Уведомления о прогнозах", callback_data=f"{CB_MAIN}predictions")],
        [InlineKeyboardButton(text="📄 Уведомления об анализах", callback_data=f"{CB_MAIN}analysis")],
        [InlineKeyboardButton(text="🔔 Все уведомления", callback_data=f"{CB_MAIN}all_on")],
        [InlineKeyboardButton(text="🔕 Отключить уведомления", callback_data=f"{CB_MAIN}all_off")],
        [InlineKeyboardButton(text="ℹ️ О боте", callback_data=f"{CB_MAIN}about")],
    ]
)
