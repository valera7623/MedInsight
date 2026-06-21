"""Send MedInsight event notifications via Telegram."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.models import (
    EVENT_ANALYSIS_COMPLETED,
    EVENT_LIMIT_EXCEEDED,
    EVENT_PATIENT_CREATED,
    EVENT_PREDICTION_READY,
)
from app.config import settings
from app.database import SessionLocal
from app.bot.services.user_service import TelegramUserService

logger = logging.getLogger(__name__)

_service: "TelegramNotificationService | None" = None


class TelegramNotificationService:
    def __init__(self, bot: Bot | None = None) -> None:
        self._bot = bot

    @property
    def enabled(self) -> bool:
        return bool(settings.TELEGRAM_BOT_ENABLED and settings.TELEGRAM_BOT_TOKEN)

    def _bot_instance(self) -> Bot | None:
        if self._bot is not None:
            return self._bot
        if not self.enabled:
            return None
        return Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

    def _frontend_url(self, path: str) -> str:
        base = (settings.FRONTEND_URL or "").rstrip("/")
        return f"{base}{path}"

    async def _send_text(self, chat_id: int, text: str) -> bool:
        bot = self._bot_instance()
        if bot is None:
            return False
        try:
            await bot.send_message(chat_id, text, disable_web_page_preview=False)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram send failed for chat %s: %s", chat_id, exc)
            return False
        finally:
            if self._bot is None and bot is not None:
                await bot.session.close()

    async def _send_to_user(self, user_id: int, event: str, text: str) -> bool:
        if not self.enabled:
            return False
        db = SessionLocal()
        try:
            svc = TelegramUserService(db)
            row = svc.get_by_user_id(user_id)
            if not row or not row.is_active:
                return False
            if event not in (row.subscription_events or []):
                return False
            return await self._send_text(row.telegram_user_id, text)
        finally:
            db.close()

    async def _send_to_tenant(self, tenant_id: int, event: str, text: str) -> int:
        if not self.enabled:
            return 0
        db = SessionLocal()
        sent = 0
        try:
            svc = TelegramUserService(db)
            for row in svc.get_active_for_tenant_event(tenant_id, event):
                if await self._send_text(row.telegram_user_id, text):
                    sent += 1
        finally:
            db.close()
        return sent

    async def send_prediction_ready(
        self,
        user_id: int,
        patient_name: str,
        prediction_id: int,
        *,
        patient_id: int,
        risk: float | int,
        confidence: float | int,
    ) -> bool:
        url = self._frontend_url(f"/patient/{patient_id}")
        text = (
            f"🧬 <b>Прогноз готов</b> для пациента {patient_name}!\n"
            f"Риск: {risk}%\n"
            f"Уверенность: {confidence}%\n"
            f"👉 <a href=\"{url}\">Открыть в MedInsight</a>"
        )
        return await self._send_to_user(user_id, EVENT_PREDICTION_READY, text)

    async def send_analysis_completed(
        self,
        user_id: int,
        patient_name: str,
        analysis_id: int,
        result_summary: str,
        *,
        patient_id: int,
    ) -> bool:
        url = self._frontend_url(f"/patient/{patient_id}")
        text = (
            f"📊 <b>Анализ завершён</b> для пациента {patient_name}!\n"
            f"Результат: {result_summary}\n"
            f"👉 <a href=\"{url}\">Открыть в MedInsight</a>"
        )
        return await self._send_to_user(user_id, EVENT_ANALYSIS_COMPLETED, text)

    async def send_limit_exceeded(
        self,
        tenant_id: int,
        plan_type: str,
        limit: int,
        remaining: int,
    ) -> int:
        pricing_url = self._frontend_url("/admin")
        text = (
            f"⚠️ <b>Лимит анализов превышен!</b>\n"
            f"Ваш тариф: {plan_type}\n"
            f"Лимит: {limit}/месяц\n"
            f"Осталось: {remaining}\n"
            f"💳 <a href=\"{pricing_url}\">Обновите тариф</a>"
        )
        return await self._send_to_tenant(tenant_id, EVENT_LIMIT_EXCEEDED, text)

    async def send_patient_created(
        self,
        user_id: int,
        patient_name: str,
        patient_id: int,
    ) -> bool:
        url = self._frontend_url(f"/patient/{patient_id}")
        text = (
            f"👤 <b>Новый пациент добавлен!</b>\n"
            f"Имя: {patient_name}\n"
            f"ID: {patient_id}\n"
            f"👉 <a href=\"{url}\">Открыть карточку</a>"
        )
        return await self._send_to_user(user_id, EVENT_PATIENT_CREATED, text)

    async def send_bulk_notification(self, user_ids: list[int], message: str) -> dict[str, Any]:
        sent = 0
        failed = 0
        db = SessionLocal()
        try:
            svc = TelegramUserService(db)
            for uid in user_ids:
                row = svc.get_by_user_id(uid)
                if not row or not row.is_active:
                    failed += 1
                    continue
                if await self._send_text(row.telegram_user_id, message):
                    sent += 1
                else:
                    failed += 1
        finally:
            db.close()
        return {"sent": sent, "failed": failed}

    # Sync wrappers for Celery / sync middleware
    def send_prediction_ready_sync(self, **kwargs) -> bool:
        return self._run_sync(self.send_prediction_ready(**kwargs))

    def send_analysis_completed_sync(self, **kwargs) -> bool:
        return self._run_sync(self.send_analysis_completed(**kwargs))

    def send_limit_exceeded_sync(self, **kwargs) -> int:
        return self._run_sync(self.send_limit_exceeded(**kwargs))

    def send_patient_created_sync(self, **kwargs) -> bool:
        return self._run_sync(self.send_patient_created(**kwargs))

    @staticmethod
    def _run_sync(coro):
        try:
            return asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram notification failed: %s", exc)
            return False


def get_notification_service() -> TelegramNotificationService:
    global _service
    if _service is None:
        _service = TelegramNotificationService()
    return _service
