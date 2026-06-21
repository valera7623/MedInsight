# API — DICOM

Префикс: `/api/dicom`  
Требует: Bearer token

## POST /api/dicom/upload

Загрузка DICOM-файла (multipart).

| Поле | Тип | Описание |
|------|-----|----------|
| file | file | `.dcm` |
| patient_id | int | ID пациента |

```bash
curl -X POST http://localhost:8000/api/dicom/upload \
  -H "Authorization: Bearer TOKEN" \
  -F "file=@scan.dcm" \
  -F "patient_id=1"
```

**Ответ 201:**

```json
{
  "id": 3,
  "study_uid": "1.2.840.113619.2.55.3...",
  "status": "processing",
  "patient_id": 1
}
```

## GET /api/dicom/studies

Список исследований.

**Query:** `patient_id`, `modality`, `status`, `search`, `skip`, `limit`

```bash
curl -H "Authorization: Bearer TOKEN" \
  "http://localhost:8000/api/dicom/studies?modality=CT&limit=20"
```

**Ответ:**

```json
{
  "items": [
    {
      "id": 3,
      "study_uid": "1.2.840...",
      "modality": "CT",
      "study_description": "Chest CT",
      "body_part": "CHEST",
      "status": "ready",
      "frame_count": 120,
      "thumbnail_url": "/api/dicom/studies/3/thumbnail"
    }
  ],
  "total": 5
}
```

## GET /api/dicom/studies/{study_id}

Детали исследования + серии.

## GET /api/dicom/studies/{study_id}/viewer

Данные для вьюера (серии, frames, window/level).

## GET /api/dicom/studies/{study_id}/thumbnail

PNG-превью (первый кадр).

## GET /api/dicom/frames/{frame_id}/image

PNG конкретного кадра.

## DELETE /api/dicom/studies/{study_id}

Удаление (admin).

## Статусы

| status | Описание |
|--------|----------|
| processing | Celery обрабатывает |
| ready | Готово к просмотру |
| failed | Ошибка парсинга |

## Ошибки

| Код | Причина |
|-----|---------|
| 413 | Превышен DICOM_MAX_FILE_SIZE_MB |
| 422 | Невалидный DICOM |

## Frontend routes

| URL | Описание |
|-----|----------|
| `/dicom` | Список |
| `/dicom/viewer/{study_uid}` | Вьюер |
