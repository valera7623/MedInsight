# API — Пациенты

Префикс: `/api/patients`  
Требует: `Authorization: Bearer TOKEN`

## GET /api/patients

Список пациентов (с учётом RBAC).

**Query:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| skip | int | Смещение (default 0) |
| limit | int | Лимит (default 20) |
| search | string | Поиск по ФИО/телефону |
| department_id | int | Фильтр отделения |

```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/patients?limit=10&search=Иванов"
```

**Ответ 200:**

```json
{
  "items": [
    {
      "id": 1,
      "full_name": "Иванов Иван",
      "date_of_birth": "1980-05-15",
      "gender": "male",
      "phone": "+79001234567",
      "department_id": 1
    }
  ],
  "total": 42
}
```

## POST /api/patients

Создание пациента.

**Тело:**

| Поле | Тип | Обязательно |
|------|-----|-------------|
| full_name | string | да |
| date_of_birth | date | да |
| gender | string | да |
| phone | string | да |
| email | string | нет |
| department_id | int | да |

## GET /api/patients/{id}

Карточка пациента с документами и прогнозами.

## PUT /api/patients/{id}

Обновление (WRITE_ROLES).

## DELETE /api/patients/{id}

Удаление (только admin).

## GET /api/patients/export/excel

Экспорт списка в Excel.

## GET /api/patients/{id}/export/pdf

PDF-отчёт по пациенту.

## Ошибки

| Код | Причина |
|-----|---------|
| 403 | Нет доступа к пациенту/отделению |
| 404 | Пациент не найден |

## Анонимизация

Для роли `researcher` поля `full_name`, `phone`, `email` маскируются в ответах.
