# Схема базы данных

## ER-диаграмма (основные сущности)

```mermaid
erDiagram
    Tenant ||--o{ User : has
    Tenant ||--o{ Patient : has
    Tenant ||--o{ Department : has
    Department ||--o{ Patient : contains
    Patient ||--o{ Document : has
    Patient ||--o{ Prediction : has
    Patient ||--o{ DicomStudy : has
    User ||--o{ Document : uploads
    User }o--|| Department : belongs
    DicomStudy ||--o{ DicomSeries : contains
    DicomSeries ||--o{ DicomFrame : contains
    Document ||--o{ ParsedData : extracts
    Tenant ||--o{ Subscription : has
    User ||--o| UserPreference : has
    User ||--o| TelegramUser : links
```

## Основные таблицы

### tenants

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | |
| name | VARCHAR | Название клиники |
| subdomain | VARCHAR UNIQUE | Поддомен для входа |

### users

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | |
| tenant_id | FK | Клиника |
| email | VARCHAR UNIQUE | |
| role | ENUM | RBAC-роль |
| department_id | FK nullable | Отделение |
| `password_hash` | VARCHAR | bcrypt hash |

### patients

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | |
| tenant_id | FK | |
| department_id | FK | |
| full_name | VARCHAR | Шифруется при необходимости |
| date_of_birth | DATE | |
| attending_doctor_id | FK nullable | |

### documents

| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER PK | |
| patient_id | FK | |
| file_path | VARCHAR | Зашифрованный путь |
| status | ENUM | uploaded/processing/parsed/failed |
| document_type | VARCHAR | |

### dicom_studies / dicom_series / dicom_frames

Иерархия DICOM: Study → Series → Frame (PNG preview).

### predictions

| Поле | Тип | Описание |
|------|-----|----------|
| readmission_risk | FLOAT | 0–1 |
| complication_risk | FLOAT | 0–1 |
| risk_level | VARCHAR | low/medium/high |
| gpt_explanation | TEXT | |

## Миграции

**Legacy:** SQL/Python-файлы в `app/db/migrations/` (001–031) — заморожены; применяются через `run_migrations()` после `create_all` при `ALEMBIC_ENABLED=false`.

**Alembic (рекомендуется для prod):** каталог `alembic/`, baseline `001_baseline`. Включите `ALEMBIC_ENABLED=true` — тогда `deploy.sh` выполняет `alembic upgrade head` (с `pg_advisory_lock` на PostgreSQL) вместо `create_all`.

```bash
# Локально / в контейнере
docker compose exec app alembic upgrade head

# Или через deploy helper
python scripts/run_alembic_migrate.py
```

## Генерация схемы

Просмотр моделей (пакет `app/models/`):

```bash
grep "^class " app/models/*.py
```

## Индексы

- `patients(tenant_id, department_id)`
- `documents(patient_id, status)`
- `dicom_studies(patient_id, study_uid)`

## Анонимизация (researcher)

В `access.py` поля `full_name`, `phone`, `email` заменяются на `P-{id} ANON` при сериализации.
