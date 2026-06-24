"""Generate dates and appointments from recurrence rules."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Appointment, AppointmentRecurring


class RecurringService:
    def generate_recurring_dates(
        self,
        rule: dict,
        from_date: date,
        until: date,
    ) -> list[date]:
        recurrence_type = rule.get("recurrence_type", "weekly")
        interval = max(1, int(rule.get("recurrence_interval", 1)))
        recurrence_days = rule.get("recurrence_days") or []
        max_count = rule.get("recurrence_count")
        recurrence_until = rule.get("recurrence_until")
        if recurrence_until and isinstance(recurrence_until, str):
            recurrence_until = date.fromisoformat(recurrence_until)
        end_date = until
        if recurrence_until and recurrence_until < end_date:
            end_date = recurrence_until

        dates: list[date] = []
        current = from_date

        if recurrence_type == "daily":
            while current <= end_date:
                if current > from_date:
                    dates.append(current)
                if max_count and len(dates) >= max_count:
                    break
                current += timedelta(days=interval)
        elif recurrence_type == "weekly":
            weekdays = {int(d) for d in recurrence_days} if recurrence_days else {current.weekday()}
            week_start = current - timedelta(days=current.weekday())
            while week_start <= end_date:
                for wd in sorted(weekdays):
                    candidate = week_start + timedelta(days=wd)
                    if candidate > from_date and candidate <= end_date:
                        dates.append(candidate)
                        if max_count and len(dates) >= max_count:
                            return dates
                week_start += timedelta(weeks=interval)
        elif recurrence_type == "monthly":
            day = current.day
            cursor = current
            while cursor <= end_date:
                if cursor > from_date:
                    dates.append(cursor)
                if max_count and len(dates) >= max_count:
                    break
                year = cursor.year
                month = cursor.month + interval
                while month > 12:
                    month -= 12
                    year += 1
                last_day = monthrange(year, month)[1]
                cursor = date(year, month, min(day, last_day))
        elif recurrence_type == "custom":
            custom_days = rule.get("recurrence_days") or []
            cursor = from_date + timedelta(days=1)
            while cursor <= end_date:
                if cursor.day in {int(d) for d in custom_days}:
                    dates.append(cursor)
                    if max_count and len(dates) >= max_count:
                        break
                cursor += timedelta(days=1)
        return dates

    def get_next_occurrence(self, rule: dict, from_date: date) -> date | None:
        until = from_date + timedelta(days=365)
        dates = self.generate_recurring_dates(rule, from_date, until)
        return dates[0] if dates else None

    def create_appointments_from_rule(
        self,
        db: Session,
        source: Appointment,
        rule_row: AppointmentRecurring,
        *,
        horizon_days: int = 90,
    ) -> list[Appointment]:
        rule = {
            "recurrence_type": rule_row.recurrence_type,
            "recurrence_interval": rule_row.recurrence_interval,
            "recurrence_days": rule_row.recurrence_days,
            "recurrence_until": rule_row.recurrence_until,
            "recurrence_count": rule_row.recurrence_count,
        }
        from_date = source.start_time.date()
        until = from_date + timedelta(days=horizon_days)
        if rule_row.recurrence_until:
            until = min(until, rule_row.recurrence_until)

        existing_starts = {
            a.start_time
            for a in db.query(Appointment).filter(
                Appointment.tenant_id == source.tenant_id,
                Appointment.doctor_id == source.doctor_id,
                Appointment.status != "cancelled",
            ).all()
        }

        created: list[Appointment] = []
        for occ_date in self.generate_recurring_dates(rule, from_date, until):
            start = datetime.combine(occ_date, source.start_time.time())
            if start in existing_starts or start <= source.start_time:
                continue
            end = start + timedelta(minutes=source.duration_minutes)
            appt = Appointment(
                tenant_id=source.tenant_id,
                patient_id=source.patient_id,
                doctor_id=source.doctor_id,
                created_by=source.created_by,
                appointment_type_id=source.appointment_type_id,
                status="scheduled",
                start_time=start,
                end_time=end,
                duration_minutes=source.duration_minutes,
                title=source.title,
                description=source.description,
                notes=source.notes,
                patient_document_id=source.patient_document_id,
                dicom_study_id=source.dicom_study_id,
                prediction_id=source.prediction_id,
                remind_before_minutes=source.remind_before_minutes,
            )
            db.add(appt)
            created.append(appt)
        if created:
            db.commit()
            for appt in created:
                db.refresh(appt)
        return created
