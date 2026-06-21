"""Settings inline keyboard with per-event toggles."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.models import ALL_SUBSCRIPTION_EVENTS, CB_SETTINGS, CB_TOGGLE, EVENT_LABELS


def settings_menu_keyboard(subscriptions: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for event in ALL_SUBSCRIPTION_EVENTS:
        label = EVENT_LABELS.get(event, event)
        enabled = event in subscriptions
        status = "вкл" if enabled else "выкл"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🔔 {label} ({status})",
                    callback_data=f"{CB_TOGGLE}{event}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"{CB_SETTINGS}back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
