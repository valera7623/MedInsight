# API — обзор

MedInsight предоставляет REST API на FastAPI.

## Базовый URL

```
https://medinsight.fileguardian.info/api
```

Локально: `http://localhost:8000/api`

## Интерактивная документация

| URL | Формат |
|-----|--------|
| `/docs` | Swagger UI (OpenAPI 3) |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI JSON |

OpenAPI **генерируется автоматически** из кода FastAPI.

## Аутентификация

JWT Bearer token:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://example.com/api/patients
```

Получение токена: [auth.md](auth.md)

## Формат ответов

Успех — JSON с данными.

Ошибки:

```json
{
  "detail": "Сообщение об ошибке"
}
```

| Код | Значение |
|-----|----------|
| 400 | Неверный запрос |
| 401 | Не авторизован |
| 403 | Нет прав |
| 404 | Не найдено |
| 402 | Лимит тарифа |
| 422 | Ошибка валидации |
| 500 | Ошибка сервера |

## Пагинация

Списки поддерживают `skip` и `limit`:

```
GET /api/patients?skip=0&limit=20
```

## Мультитенантность

При регистрации/логине указывается `subdomain` клиники. JWT содержит `tenant_id` — все данные изолированы.

## Разделы API

| Документ | Префикс |
|----------|---------|
| [Аутентификация](auth.md) | `/api/auth` |
| [Пациенты](patients.md) | `/api/patients` |
| [Документы](documents.md) | `/api/documents` |
| [DICOM](dicom.md) | `/api/dicom` |
| [Аналитика](analytics.md) | `/api/analytics`, `/api/dashboard` |
| [Прогнозы](predictions.md) | `/api/predictions` |

## WebSocket

```
ws://host/ws/notifications?token=JWT
```

События: `document_parsed`, `prediction_ready`, `dicom_processed`.

## Rate limiting

На проде рекомендуется nginx rate limit. В приложении — лимиты тарифа на прогнозы.

## Версионирование

Текущая версия API не версионирована в URL. Breaking changes документируются в [Changelog](../misc/changelog.md).
