# MedInsight

Платформа клинической аналитики — MVP для загрузки медицинских документов, извлечения сущностей, визуализации статистики и GPT-прогнозирования рисков.

## Стек

- **Backend:** FastAPI, SQLAlchemy, SQLite
- **Auth:** JWT (7 дней)
- **NLP:** spaCy `ru_core_news_lg`
- **Parsing:** python-docx, PyPDF2
- **Async:** Celery + Redis
- **AI:** OpenAI GPT через [ProxyAPI](https://proxyapi.ru)
- **Frontend:** Vanilla JS + Chart.js
- **Deploy:** Docker + Traefik

## Требования

- **Python 3.11–3.12** — рекомендуется для локальной разработки со spaCy
- **Python 3.14** — работает без spaCy (regex-only NER); для spaCy используйте Docker
- **Docker** — предпочтительный способ деплоя (Python 3.12 + spaCy + Celery внутри образа)
- **Redis** — брокер для Celery (включён в docker-compose)

## Быстрый старт (локально)

```bash
cd medinsight
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Запустить Redis (отдельный терминал)
docker run -d -p 6379:6379 redis:7-alpine

# Обновить .env для локального Redis:
# REDIS_URL=redis://localhost:6379/0
# CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Терминал 1: API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Терминал 2: Celery worker
celery -A app.tasks.celery_app worker --loglevel=info
```

Открыть:
- http://localhost:8000/login — вход
- http://localhost:8000/ — дашборд
- http://localhost:8000/patient/1 — карточка пациента с прогнозами
- http://localhost:8000/docs — Swagger UI

## Docker

```bash
cp .env.example .env
chmod +x deploy.sh
./deploy.sh          # dev: app + redis + celery
./deploy.sh production  # prod на :8000
```

## Настройка ProxyAPI

MedInsight использует [ProxyAPI](https://proxyapi.ru) как прокси к OpenAI API. Это позволяет работать с GPT из России без VPN.

1. Зарегистрируйтесь на https://proxyapi.ru
2. Получите API-ключ в личном кабинете
3. Добавьте в `.env`:

```env
OPENAI_API_KEY=ваш_ключ_из_ProxyAPI
OPENAI_BASE_URL=https://api.proxyapi.ru/openai/v1
OPENAI_MODEL=gpt-4o-mini
```

4. Перезапустите сервисы:

```bash
./deploy.sh
# или локально: перезапустите uvicorn и celery worker
```

**Поведение при ошибках:**
- HTTP 401/404 — ошибка авторизации или маршрутизации (проверьте ключ и `OPENAI_BASE_URL`)
- HTTP 429 — rate limit, автоматический retry (до 3 попыток)
- HTTP 5xx — ошибка сервера ProxyAPI, retry с exponential backoff
- Если GPT недоступен — fallback на rule-based прогнозы (без GPT)

**Безопасность:** API-ключ OpenAI/ProxyAPI никогда не логируется.

## Автодеплой (GitHub Actions → VPS)

Подробная инструкция: **[DEPLOY.md](DEPLOY.md)**

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
| POST | `/api/documents/upload` | Загрузить DOCX/PDF (асинхронный парсинг) |
| GET | `/api/documents/{id}` | Документ с parsed_data и статусом |
| GET | `/api/documents/patient/{patient_id}` | Документы пациента |

### Аналитика (JWT required)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/analytics/dashboard` | Данные для дашборда |
| GET | `/api/analytics/dashboard/predictions` | Дашборд прогнозов |

### Прогнозы (JWT required, Фаза 2)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/analytics/predict/{patient_id}` | Запустить асинхронный прогноз |
| GET | `/api/analytics/predict/status/{job_id}` | Статус задачи прогноза |
| GET | `/api/analytics/predictions/{patient_id}` | Все прогнозы пациента |
| POST | `/api/analytics/insights/{patient_id}` | AI-инсайты (GPT) |
| POST | `/api/analytics/validate-prediction/{prediction_id}` | Подтвердить прогноз |

### Экспорт (JWT required)

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/export/patient/{patient_id}` | PDF-отчёт по пациенту |

## Тестовый скрипт (Фаза 2)

```bash
pip install httpx python-docx
python scripts/test_predict.py http://localhost:8000
```

Скрипт: создаёт пациента → загружает документ → ждёт парсинг → запускает прогноз → показывает результат.

## Примеры curl

### Запустить прогноз

```bash
curl -X POST http://localhost:8000/api/analytics/predict/1 \
  -H "Authorization: Bearer $TOKEN"
# {"job_id":"1","status":"pending"}

curl http://localhost:8000/api/analytics/predict/status/1 \
  -H "Authorization: Bearer $TOKEN"
```

### AI-инсайты

```bash
curl -X POST http://localhost:8000/api/analytics/insights/1 \
  -H "Authorization: Bearer $TOKEN"
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `SECRET_KEY` | Ключ для JWT | — |
| `DATABASE_URL` | URL базы данных | `sqlite:///./medinsight.db` |
| `STORAGE_PATH` | Путь к файлам | `./storage` |
| `REDIS_URL` | Redis брокер Celery | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Redis для результатов | `redis://redis:6379/1` |
| `OPENAI_API_KEY` | Ключ ProxyAPI/OpenAI | — |
| `OPENAI_BASE_URL` | Base URL ProxyAPI | `https://api.proxyapi.ru/openai/v1` |
| `OPENAI_MODEL` | Модель GPT | `gpt-4o-mini` |
| `SPACY_MODEL` | Модель spaCy | `ru_core_news_lg` |

## Роли

- `doctor` — стандартный доступ
- `researcher` — стандартный доступ
- `admin` — может удалять пациентов

## Лицензия

MIT
