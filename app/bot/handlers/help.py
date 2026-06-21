""" /help — bot command reference."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")

HELP_TEXT = (
    "📖 <b>Справка MedInsight Bot</b>\n\n"
    "<b>Привязка аккаунта</b>\n"
    "1. /start — получите 6-значный код\n"
    "2. Введите код в настройках профиля на сайте MedInsight\n\n"
    "<b>Команды</b>\n"
    "/menu — главное меню\n"
    "/settings — настройка типов уведомлений\n"
    "/subscribe — включить все уведомления\n"
    "/unsubscribe — отключить все уведомления\n"
    "/status — статус привязки и подписок\n"
    "/help — эта справка\n\n"
    "<b>Типы уведомлений</b>\n"
    "• Прогнозы риска\n"
    "• Завершение анализа документов\n"
    "• Превышение лимитов\n"
    "• Новые пациенты"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
