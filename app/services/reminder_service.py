"""Appointment reminders via Telegram, email, and WebSocket."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Appointment, Patient, User
from app.services.email import EmailService
from app.websocket.events import EVENT_APPOINTMENT_REMINDER, publish_event

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"scheduled", "confirmed"})


class ReminderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._email = EmailService()

    def get_reminder_channels(self, appointment: Appointment) -> list[str]:
        channels: list[str] = ["websocket"]
        doctor = self.db.query(User).filter(User.id == appointment.doctor_id).first()
        patient = self.db.query(Patient).filter(Patient.id == appointment.patient_id).first()
        if doctor and settings.TELEGRAM_BOT_ENABLED:
            channels.append("telegram")
        if (doctor and doctor.email) or (patient and patient.email):
            if settings.EMAIL_ENABLED:
                channels.append("email")
        return channels

    def schedule_reminder(self, appointment_id: int) -> None:
        """Mark appointment as pending reminder (actual send is batch-driven)."""
        appt = self.db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appt:
            return
        appt.reminder_sent = False
        appt.reminder_sent_at = None
        self.db.commit()

    def send_reminder(self, appointment_id: int) -> bool:
        appt = (
            self.db.query(Appointment)
            .filter(Appointment.id == appointment_id, Appointment.reminder_sent.is_(False))
            .first()
        )
        if not appt or appt.status not in ACTIVE_STATUSES:
            return False

        now = datetime.utcnow()
        remind_at = appt.start_time - timedelta(minutes=appt.remind_before_minutes)
        if now < remind_at:
            return False

        patient = self.db.query(Patient).filter(Patient.id == appt.patient_id).first()
        doctor = self.db.query(User).filter(User.id == appt.doctor_id).first()
        patient_name = f"{patient.last_name} {patient.first_name}" if patient else "Пациент"
        start_fmt = appt.start_time.strftime("%d.%m.%Y %H:%M")

        plain = (
            f"Напоминание о приёме: {appt.title}\n"
            f"Пациент: {patient_name}\n"
            f"Время: {start_fmt}"
        )

        sent_any = False
        for channel in self.get_reminder_channels(appt):
            try:
                if channel == "telegram" and doctor:
                    from app.bot.services.notification_service import get_notification_service

                    if get_notification_service().send_appointment_reminder_sync(
                        user_id=doctor.id,
                        appointment_id=appt.id,
                        message=plain,
                        start_time=start_fmt,
                    ):
                        sent_any = True
                elif channel == "email":
                    if self._send_email_reminder(appt, doctor, patient, start_fmt):
                        sent_any = True
                elif channel == "websocket":
                    publish_event(
                        EVENT_APPOINTMENT_REMINDER,
                        {
                            "appointment_id": appt.id,
                            "title": appt.title,
                            "start_time": start_fmt,
                            "patient_name": patient_name,
                        },
                        user_id=appt.doctor_id,
                        tenant_id=appt.tenant_id,
                    )
                    sent_any = True
            except Exception as exc:  # noqa: BLE001
                logger.warning("Reminder channel %s failed for appt %s: %s", channel, appt.id, exc)

        if sent_any:
            appt.reminder_sent = True
            appt.reminder_sent_at = now
            self.db.commit()
        return sent_any

    def _send_email_reminder(
        self,
        appt: Appointment,
        doctor: User | None,
        patient: Patient | None,
        start_fmt: str,
    ) -> bool:
        recipients: list[str] = []
        if doctor and doctor.email:
            recipients.append(doctor.email)
        if patient and patient.email:
            recipients.append(patient.email)
        if not recipients:
            return False

        subject = f"Напоминание: {appt.title}"
        html = (
            f"<p>Напоминание о приёме <strong>{appt.title}</strong></p>"
            f"<p>Дата и время: {start_fmt}</p>"
        )
        if appt.description:
            html += f"<p>{appt.description}</p>"
        plain = (
            f"Напоминание о приёме: {appt.title}\n"
            f"Дата и время: {start_fmt}"
        )

        async def _send_all() -> bool:
            ok = False
            for to in recipients:
                if await self._email.send_email(to, subject, html, plain):
                    ok = True
            return ok

        try:
            return asyncio.run(_send_all())
        except Exception as exc:  # noqa: BLE001
            logger.warning("Email reminder failed: %s", exc)
            return False

    def send_reminders_for_upcoming_appointments(self) -> int:
        if not settings.APPOINTMENTS_ENABLED:
            return 0
        now = datetime.utcnow()
        horizon = now + timedelta(hours=48)
        appointments = (
            self.db.query(Appointment)
            .filter(
                Appointment.status.in_(ACTIVE_STATUSES),
                Appointment.reminder_sent.is_(False),
                Appointment.start_time > now,
                Appointment.start_time <= horizon,
            )
            .all()
        )
        sent = 0
        for appt in appointments:
            if self.send_reminder(appt.id):
                sent += 1
        return sent
