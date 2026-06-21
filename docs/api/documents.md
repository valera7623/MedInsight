# API — Документы

Префикс: `/api/documents`  
Требует: Bearer token

## POST /api/documents/upload

Загрузка документа (multipart/form-data).

| Поле | Тип | Описание |
|------|-----|----------|
| file | file | PDF или DOCX |
| patient_id | int | ID пациента |
| document_type | string | discharge, lab, history |

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@vypiska.pdf" \
  -F "patient_id=1" \
  -F "document_type=discharge"
```

**Ответ 201:**

```json
{
  "id": 10,
  "patient_id": 1,
  "filename": "vypiska.pdf",
  "status": "uploaded",
  "document_type": "discharge"
}
```

После загрузки Celery ставит задачу парсинга → статус `processing` → `parsed`.

## GET /api/documents

Список документов.

**Query:** `patient_id`, `status`, `skip`, `limit`

## GET /api/documents/{id}

Метаданные документа + parsed data (если готово).

**Ответ (parsed):**

```json
{
  "id": 10,
  "status": "parsed",
  "parsed_data": {
    "diagnoses": ["I10", "E11"],
    "medications": ["метформин", "эналаприл"],
    "raw_text_preview": "..."
  }
}
```

## GET /api/documents/{id}/download

Скачивание расшифрованного файла (stream).

## DELETE /api/documents/{id}

Удаление (admin / head_of_department).

## Статусы

| status | Описание |
|--------|----------|
| uploaded | Принят |
| processing | Парсинг |
| parsed | Готово |
| failed | Ошибка |

## Ошибки

| Код | Причина |
|-----|---------|
| 403 | Нет прав на пациента |
| 413 | Файл слишком большой |
| 415 | Неподдерживаемый формат |
