"""Celery tasks for appointments calendar."""

from __future__ import annotations

import logging

from app.database import SessionLocal
from app.models import AppointmentRecurring
from app.services.appointment_service import AppointmentService
from app.services.recurring_service import RecurringService
from app.services.reminder_service import ReminderService
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.appointment_tasks.process_appointment_reminders")
def process_appointment_reminders() -> int:
    """Check and send upcoming appointment reminders."""
    db = SessionLocal()
    try:
        count = ReminderService(db).send_reminders_for_upcoming_appointments()
        logger.info("Sent %d appointment reminder(s)", count)
        return count
    finally:
        db.close()


@celery_app.task(name="app.tasks.appointment_tasks.update_recurring_appointments")
def update_recurring_appointments() -> int:
    """Create next occurrences for active recurring rules."""
    db = SessionLocal()
    recurring = RecurringService()
    created_total = 0
    try:
        rules = (
            db.query(AppointmentRecurring)
            .filter(AppointmentRecurring.is_active.is_(True))
            .all()
        )
        svc = AppointmentService(db)
        for rule in rules:
            source = svc.get_appointment(rule.appointment_id, rule.tenant_id)
            if not source or source.status == "cancelled":
                continue
            created = recurring.create_appointments_from_rule(db, source, rule)
            created_total += len(created)
        logger.info("Created %d recurring appointment(s)", created_total)
        return created_total
    finally:
        db.close()


@celery_app.task(name="app.tasks.appointment_tasks.update_appointment_status")
def update_appointment_status() -> int:
    """Auto-mark missed appointments as no_show."""
    db = SessionLocal()
    try:
        count = AppointmentService(db).mark_no_shows()
        logger.info("Marked %d appointment(s) as no_show", count)
        return count
    finally:
        db.close()
