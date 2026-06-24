"""Telegram bot constants and event definitions."""

from __future__ import annotations

EVENT_PREDICTION_READY = "prediction.ready"
EVENT_ANALYSIS_COMPLETED = "analysis.completed"
EVENT_LIMIT_EXCEEDED = "limit.exceeded"
EVENT_PATIENT_CREATED = "patient.created"
EVENT_APPOINTMENT_REMINDER = "appointment.reminder"
EVENT_APPOINTMENT_CREATED = "appointment.created"

DEFAULT_SUBSCRIPTION_EVENTS = [EVENT_PREDICTION_READY, EVENT_ANALYSIS_COMPLETED]

ALL_SUBSCRIPTION_EVENTS = [
    EVENT_PREDICTION_READY,
    EVENT_ANALYSIS_COMPLETED,
    EVENT_PATIENT_CREATED,
    EVENT_LIMIT_EXCEEDED,
    EVENT_APPOINTMENT_REMINDER,
    EVENT_APPOINTMENT_CREATED,
]

EVENT_LABELS: dict[str, str] = {
    EVENT_PREDICTION_READY: "Прогнозы",
    EVENT_ANALYSIS_COMPLETED: "Анализы",
    EVENT_PATIENT_CREATED: "Новые пациенты",
    EVENT_LIMIT_EXCEEDED: "Лимиты",
    EVENT_APPOINTMENT_REMINDER: "Напоминания о приёмах",
    EVENT_APPOINTMENT_CREATED: "Новые приёмы",
}

# Inline keyboard callback prefixes
CB_MAIN = "main:"
CB_SETTINGS = "settings:"
CB_TOGGLE = "toggle:"
