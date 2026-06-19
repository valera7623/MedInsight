# MedInsight

Платформа клинической аналитики — MVP для загрузки медицинских документов, извлечения сущностей и визуализации статистики.

## Стек

- **Backend:** FastAPI, SQLAlchemy, SQLite
- **Auth:** JWT (7 дней)
- **NLP:** spaCy `ru_core_news_lg`
- **Parsing:** python-docx, PyPDF2
- **Frontend:** Vanilla JS + Chart.js
- **Deploy:** Docker + Traefik

## Требования

- **Python 3.11–3.12** — рекомендуется для локальной разработки со spaCy
- **Python 3.14** — работает без spaCy (regex-only NER); для spaCy используйте Docker
- **Docker** — предпочтительный способ деплоя (Python 3.12 + spaCy внутри образа)

## Быстрый старт (локально)

```bash
# 1. Клонировать и перейти в проект
cd medinsight

# 2. Создать виртуальное окружение (Python 3.11–3.14)
python3 -m venv .venv
source .venv/bin/activate

# 3. Установить зависимости (без spaCy — работает на Python 3.14)
pip install -r requirements.txt

# 3b. (Опционально) spaCy для улучшенного NER — только Python 3.11–3.12
# pip install -r requirements-nlp.txt
# python -m spacy download ru_core_news_lg

# 4. Настроить окружение
cp .env.example .env

# 5. Запустить
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Открыть:
- http://localhost:8000/login — вход
- http://localhost:8000/ — дашборд
- http://localhost:8000/docs — Swagger UI

## Docker

```bash
cp .env.example .env
chmod +x deploy.sh
./deploy.sh          # dev на :8000
./deploy.sh production  # prod на :8001
```

## Автодеплой (GitHub Actions → VPS)

Подробная инструкция: **[DEPLOY.md](DEPLOY.md)**

Кратко:
1. Push в `main` на https://github.com/valera7623/Medinsight
2. GitHub Secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `APP_SECRET_KEY`
3. После деплоя: http://186.246.3.65:8000/

## API Endpoints

### Аутентификация

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/register` | Регистрация |
| POST | `/api/auth/login` | Вход, получение JWT |

### Пациенты (JWT required)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/patients` | Создать пациента |
| GET | `/api/patients` | Список (пагинация) |
| GET | `/api/patients/{id}` | Карточка пациента |
| PUT | `/api/patients/{id}` | Обновить |
| DELETE | `/api/patients/{id}` | Удалить (только admin) |

### Документы (JWT required)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/documents/upload` | Загрузить DOCX/PDF |
| GET | `/api/documents/{id}` | Документ с parsed_data |
| GET | `/api/documents/patient/{patient_id}` | Документы пациента |

### Аналитика (JWT required)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/analytics/dashboard` | Данные для дашборда |

### Экспорт (JWT required)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/export/patient/{patient_id}` | PDF-отчёт по пациенту |

## Примеры curl

### Регистрация

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "doctor@clinic.ru",
    "password": "secret123",
    "full_name": "Иванов Иван",
    "role": "doctor"
  }'
```

### Вход

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "doctor@clinic.ru", "password": "secret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Создать пациента

```bash
curl -X POST http://localhost:8000/api/patients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Пётр",
    "last_name": "Сидоров",
    "middle_name": "Иванович",
    "birth_date": "1985-03-15",
    "gender": "M",
    "phone": "+79001234567"
  }'
```

### Загрузить документ

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "patient_id=1" \
  -F "document_type=discharge" \
  -F "file=@/path/to/discharge.pdf"
```

### Дашборд

```bash
curl http://localhost:8000/api/analytics/dashboard \
  -H "Authorization: Bearer $TOKEN"
```

### Экспорт PDF

```bash
curl -X POST http://localhost:8000/api/export/patient/1 \
  -H "Authorization: Bearer $TOKEN" \
  -o patient_1_report.pdf
```

## Структура parsed_data

```json
{
  "diagnoses": ["J45.0", "I10"],
  "medications": ["Амоксициллин", "Парацетамол"],
  "dates": ["2024-01-15", "2024-01-20"],
  "full_text": "..."
}
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `SECRET_KEY` | Ключ для JWT | — |
| `DATABASE_URL` | URL базы данных | `sqlite:///./medinsight.db` |
| `STORAGE_PATH` | Путь к файлам | `./storage` |
| `CORS_ORIGINS` | CORS origins | `http://localhost:5173,...` |
| `SPACY_MODEL` | Модель spaCy | `ru_core_news_lg` |

## Роли

- `doctor` — стандартный доступ
- `researcher` — стандартный доступ
- `admin` — может удалять пациентов

## Лицензия

MIT
