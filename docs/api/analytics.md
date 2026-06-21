# API — Аналитика

Префиксы: `/api/analytics`, `/api/dashboard`  
Требует: Bearer token

## GET /api/dashboard/stats

Сводная статистика для дашборда.

**Query:** `department_id` (optional)

```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/dashboard/stats?department_id=1"
```

**Ответ 200:**

```json
{
  "patients_count": 150,
  "documents_count": 320,
  "diagnoses_count": 45,
  "top_diagnoses": [
    {"code": "I10", "count": 42},
    {"code": "E11", "count": 38}
  ],
  "top_medications": [
    {"name": "метформин", "count": 55}
  ],
  "dicom_studies_count": 12,
  "dicom_by_modality": {"CT": 8, "MR": 4}
}
```

## GET /api/analytics/diagnoses

Топ диагнозов с пагинацией.

## GET /api/analytics/medications

Топ лекарств.

## GET /api/analytics/departments

Статистика по отделениям.

## GET /api/analytics/risk-summary

Сводка по рискам (high/medium/low counts).

## GET /api/analytics/recent-patients

Последние добавленные пациенты.

## GET /api/analytics/export/excel

Экспорт аналитики в Excel.

## Webhooks (admin)

### GET /api/webhooks

Список вебхуков клиники.

### POST /api/webhooks

Создание вебхука (URL + events).

### DELETE /api/webhooks/{id}

Удаление.

## RBAC

- `viewer`, `researcher` — read-only статистика;
- `researcher` — агрегаты без ПДн в детальных списках;
- экспорт — по политике роли.

## Ошибки

| Код | Причина |
|-----|---------|
| 403 | Нет доступа к отделению |
