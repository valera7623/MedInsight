"""ICS export/import and external calendar deep links."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from app.config import settings
from app.models import Appointment


def _utc_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ics_dt(dt: datetime) -> str:
    return _utc_dt(dt).strftime("%Y%m%dT%H%M%SZ")


def _escape_ics(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


class CalendarService:
    def export_to_ics(self, appointments: list[Appointment]) -> str:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//MedInsight//Appointments//RU",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        for appt in appointments:
            if appt.status == "cancelled":
                continue
            uid = f"appointment-{appt.id}@medinsight"
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{_ics_dt(datetime.utcnow())}",
                    f"DTSTART:{_ics_dt(appt.start_time)}",
                    f"DTEND:{_ics_dt(appt.end_time)}",
                    f"SUMMARY:{_escape_ics(appt.title)}",
                ]
            )
            if appt.description:
                lines.append(f"DESCRIPTION:{_escape_ics(appt.description)}")
            if appt.notes:
                lines.append(f"COMMENT:{_escape_ics(appt.notes)}")
            lines.append(f"STATUS:{appt.status.upper()}")
            lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    def import_from_ics(self, ics_content: str) -> list[dict]:
        events: list[dict] = []
        blocks = re.split(r"BEGIN:VEVENT", ics_content)
        for block in blocks[1:]:
            if "END:VEVENT" not in block:
                continue
            event_text = block.split("END:VEVENT")[0]

            def _field(name: str) -> str | None:
                match = re.search(rf"^{name}[^:]*:(.+)$", event_text, re.MULTILINE)
                return match.group(1).strip() if match else None

            start_raw = _field("DTSTART")
            end_raw = _field("DTEND")
            if not start_raw:
                continue
            events.append(
                {
                    "title": (_field("SUMMARY") or "Приём").replace("\\n", "\n"),
                    "description": (_field("DESCRIPTION") or "").replace("\\n", "\n") or None,
                    "start_time": self._parse_ics_datetime(start_raw),
                    "end_time": self._parse_ics_datetime(end_raw) if end_raw else None,
                }
            )
        return events

    def _parse_ics_datetime(self, value: str) -> datetime:
        value = value.strip()
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        if "T" in value:
            return datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
        return datetime.strptime(value[:8], "%Y%m%d")

    def get_google_calendar_url(self, appointment: Appointment) -> str:
        base = "https://calendar.google.com/calendar/render"
        params = (
            f"action=TEMPLATE"
            f"&text={quote(appointment.title)}"
            f"&dates={_ics_dt(appointment.start_time)}/{_ics_dt(appointment.end_time)}"
        )
        if appointment.description:
            params += f"&details={quote(appointment.description)}"
        frontend = (settings.FRONTEND_URL or "").rstrip("/")
        if frontend:
            params += f"&location={quote(frontend + '/appointments')}"
        return f"{base}?{params}"

    def get_outlook_calendar_url(self, appointment: Appointment) -> str:
        base = "https://outlook.live.com/calendar/0/deeplink/compose"
        params = (
            f"path=/calendar/action/compose"
            f"&subject={quote(appointment.title)}"
            f"&startdt={_utc_dt(appointment.start_time).isoformat()}"
            f"&enddt={_utc_dt(appointment.end_time).isoformat()}"
        )
        if appointment.description:
            params += f"&body={quote(appointment.description)}"
        return f"{base}?{params}"
