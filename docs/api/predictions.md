# API — Прогнозы

Префикс: `/api/predictions`  
Требует: Bearer token, WRITE_ROLES для создания

## POST /api/predictions/run

Запуск прогноза для пациента.

**Тело:**

```json
{
  "patient_id": 1
}
```

```bash
curl -X POST http://localhost:8000/api/predictions/run \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"patient_id": 1}'
```

**Ответ 202:**

```json
{
  "task_id": "abc-123",
  "status": "processing",
  "message": "Прогноз поставлен в очередь"
}
```

## GET /api/predictions/patient/{patient_id}

История прогнозов пациента.

**Ответ:**

```json
{
  "items": [
    {
      "id": 7,
      "patient_id": 1,
      "readmission_risk": 0.35,
      "complication_risk": 0.22,
      "risk_level": "medium",
      "gpt_explanation": "Пациент с сопутствующими...",
      "created_at": "2026-06-20T14:30:00Z",
      "validated": null
    }
  ]
}
```

## GET /api/predictions/high-risk

Пациенты с высоким риском (дашборд).

**Query:** `department_id`, `limit`

## POST /api/predictions/{id}/validate

Валидация прогноза врачом.

**Тело:**

```json
{
  "is_accurate": true,
  "comment": "Согласен с оценкой"
}
```

## GET /api/predictions/export/excel

Экспорт прогнозов в Excel.

## Лимиты тарифа

При превышении месячного лимита:

**Ответ 402:**

```json
{
  "detail": "Monthly analysis limit exceeded",
  "limit": 5,
  "used": 5
}
```

## Асинхронность

Результат доступен после завершения Celery-задачи. Подпишитесь на WebSocket или опрашивайте `GET /api/predictions/patient/{id}`.

## Fallback

Если GPT недоступен, `gpt_explanation` может быть `null`, риски рассчитываются rule-based.
