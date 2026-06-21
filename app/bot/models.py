"""Telegram bot constants and event definitions."""

from __future__ import annotations

EVENT_PREDICTION_READY = "prediction.ready"
EVENT_ANALYSIS_COMPLETED = "analysis.completed"
EVENT_LIMIT_EXCEEDED = "limit.exceeded"
EVENT_PATIENT_CREATED = "patient.created"

DEFAULT_SUBSCRIPTION_EVENTS = [EVENT_PREDICTION_READY, EVENT_ANALYSIS_COMPLETED]

ALL_SUBSCRIPTION_EVENTS = [
    EVENT_PREDICTION_READY,
    EVENT_ANALYSIS_COMPLETED,
    EVENT_PATIENT_CREATED,
    EVENT_LIMIT_EXCEEDED,
]

EVENT_LABELS: dict[str, str] = {
    EVENT_PREDICTION_READY: "Прогнозы",
    EVENT_ANALYSIS_COMPLETED: "Анализы",
    EVENT_PATIENT_CREATED: "Новые пациенты",
    EVENT_LIMIT_EXCEEDED: "Лимиты",
}

# Inline keyboard callback prefixes
CB_MAIN = "main:"
CB_SETTINGS = "settings:"
CB_TOGGLE = "toggle:"
