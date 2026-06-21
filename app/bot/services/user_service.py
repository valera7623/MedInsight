"""Telegram user linking and subscription management."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.bot.models import ALL_SUBSCRIPTION_EVENTS, DEFAULT_SUBSCRIPTION_EVENTS
from app.models import TelegramUser, User

logger = logging.getLogger(__name__)


class TelegramUserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_telegram_id(self, telegram_user_id: int) -> TelegramUser | None:
        return (
            self.db.query(TelegramUser)
            .filter(TelegramUser.telegram_user_id == telegram_user_id)
            .first()
        )

    def get_by_user_id(self, user_id: int) -> TelegramUser | None:
        return self.db.query(TelegramUser).filter(TelegramUser.user_id == user_id).first()

    def link_user(
        self,
        *,
        telegram_user_id: int,
        medinsight_user_id: int,
        telegram_username: str | None = None,
        first_name: str = "",
        last_name: str | None = None,
        subscription_events: list[str] | None = None,
    ) -> bool:
        user = self.db.query(User).filter(User.id == medinsight_user_id).first()
        if not user:
            return False

        events = subscription_events or list(DEFAULT_SUBSCRIPTION_EVENTS)
        existing = self.get_by_telegram_id(telegram_user_id)
        if existing:
            existing.user_id = medinsight_user_id
            existing.telegram_username = telegram_username
            existing.first_name = first_name or existing.first_name
            existing.last_name = last_name
            existing.is_active = True
            existing.subscription_events = events
            existing.updated_at = datetime.utcnow()
        else:
            # Unlink any previous Telegram binding for this MedInsight user.
            prior = self.get_by_user_id(medinsight_user_id)
            if prior and prior.telegram_user_id != telegram_user_id:
                prior.is_active = False
                prior.updated_at = datetime.utcnow()

            self.db.add(
                TelegramUser(
                    user_id=medinsight_user_id,
                    telegram_user_id=telegram_user_id,
                    telegram_username=telegram_username,
                    first_name=first_name or "User",
                    last_name=last_name,
                    is_active=True,
                    subscription_events=events,
                )
            )

        self.db.commit()
        return True

    def unlink_user(self, telegram_user_id: int) -> bool:
        row = self.get_by_telegram_id(telegram_user_id)
        if not row:
            return False
        row.is_active = False
        row.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def unlink_by_medinsight_user(self, user_id: int) -> bool:
        row = self.get_by_user_id(user_id)
        if not row:
            return False
        row.is_active = False
        row.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def get_medinsight_user(self, telegram_user_id: int) -> User | None:
        row = self.get_by_telegram_id(telegram_user_id)
        if not row or not row.is_active:
            return None
        return self.db.query(User).filter(User.id == row.user_id).first()

    def get_subscriptions(self, telegram_user_id: int) -> list[str]:
        row = self.get_by_telegram_id(telegram_user_id)
        if not row or not row.is_active:
            return []
        return list(row.subscription_events or [])

    def update_subscriptions(self, telegram_user_id: int, events: list[str]) -> bool:
        row = self.get_by_telegram_id(telegram_user_id)
        if not row or not row.is_active:
            return False
        cleaned = [e for e in events if e in ALL_SUBSCRIPTION_EVENTS]
        row.subscription_events = cleaned
        row.updated_at = datetime.utcnow()
        self.db.commit()
        return True

    def toggle_subscription(self, telegram_user_id: int, event: str) -> list[str]:
        current = self.get_subscriptions(telegram_user_id)
        if event in current:
            current = [e for e in current if e != event]
        else:
            current = sorted(set(current + [event]))
        self.update_subscriptions(telegram_user_id, current)
        return current

    def subscribe_all(self, telegram_user_id: int) -> bool:
        return self.update_subscriptions(telegram_user_id, list(ALL_SUBSCRIPTION_EVENTS))

    def unsubscribe_all(self, telegram_user_id: int) -> bool:
        return self.update_subscriptions(telegram_user_id, [])

    def get_all_active_users(self) -> list[TelegramUser]:
        return (
            self.db.query(TelegramUser)
            .filter(TelegramUser.is_active.is_(True))
            .all()
        )

    def get_active_for_tenant_event(self, tenant_id: int, event: str) -> list[TelegramUser]:
        rows = (
            self.db.query(TelegramUser)
            .join(User, TelegramUser.user_id == User.id)
            .filter(
                TelegramUser.is_active.is_(True),
                User.tenant_id == tenant_id,
            )
            .all()
        )
        return [r for r in rows if event in (r.subscription_events or [])]
