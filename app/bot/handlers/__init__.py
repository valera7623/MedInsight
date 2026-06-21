"""Register all bot handlers."""

from aiogram import Router

from app.bot.handlers import help as help_handler
from app.bot.handlers import menu as menu_handler
from app.bot.handlers import settings as settings_handler
from app.bot.handlers import start as start_handler
from app.bot.handlers import status as status_handler
from app.bot.handlers import subscribe as subscribe_handler
from app.bot.handlers import unsubscribe as unsubscribe_handler


def setup_routers() -> Router:
    root = Router(name="medinsight_bot")
    root.include_router(start_handler.router)
    root.include_router(menu_handler.router)
    root.include_router(settings_handler.router)
    root.include_router(subscribe_handler.router)
    root.include_router(unsubscribe_handler.router)
    root.include_router(status_handler.router)
    root.include_router(help_handler.router)
    return root
