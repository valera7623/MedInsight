# MedInsight

Платформа клинической аналитики — MVP для загрузки медицинских документов, извлечения сущностей, визуализации статистики и GPT-прогнозирования рисков.

## Стек

- **Backend:** FastAPI, SQLAlchemy, SQLite (dev) / PostgreSQL (production)
- **Auth:** JWT (7 дней)
- **NLP:** spaCy `ru_core_news_lg`
- **Parsing:** python-docx, PyPDF2
- **Async:** Celery + Redis
- **AI:** OpenAI GPT через [ProxyAPI](https://proxyapi.ru)
- **Frontend:** Vanilla JS + Chart.js
- **Deploy:** Docker + Traefik
- **Security (Phase 3):** Multi-tenancy, RBAC, age encryption
- **Phase 4:** Self-healing RAG (ChromaDB), вебхуки (HMAC), платежи (Stripe + ЮKassa)

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
./deploy.sh          # dev: SQLite + app + redis + celery
./deploy.sh production  # prod: PostgreSQL + Traefik HTTPS
```

## PostgreSQL (production)

Production использует **PostgreSQL 15** вместо SQLite:

| Возможность | SQLite (dev) | PostgreSQL (prod) |
|-------------|--------------|-------------------|
| Конкурентные записи | блокировка файла | MVCC, пул соединений |
| JSON-поля | JSON (TEXT) | **JSONB** + GIN-индексы |
| Поиск | ILIKE | **полнотекстовый** (`tsvector`, `to_tsquery`) |
| Публичные ID | `public_id` (UUID string) | **UUID** (native) |
| Бэкап | копия `.db` | **pg_dump** / **pg_restore** |
| Аудит | приложение | **триггеры** в БД → `audit_logs.details` (JSONB) |

### Быстрый старт (production)

```bash
cp .env.example .env
# Задайте POSTGRES_PASSWORD и PRODUCTION_DATABASE_URL
./deploy.sh production
```

Docker Compose поднимает сервис `postgres:15-alpine` с healthcheck и volume `medinsight-postgres`.

### Миграция SQLite → PostgreSQL

```bash
docker compose exec app python scripts/migrate_to_postgres.py \
  --sqlite-url sqlite:////app/data/medinsight.db \
  --postgres-url "postgresql://medinsight:PASSWORD@postgres:5432/medinsight"
```

### Проверка PostgreSQL

```bash
docker compose exec app python scripts/test_postgres.py
```

Проверяет: подключение, миграции (019), полнотекстовый поиск по пациентам.

Подробнее: **[DEPLOY.md](DEPLOY.md)** (раздел «PostgreSQL в production»).

## API documentation generation

English API reference is **auto-generated** from the FastAPI OpenAPI schema.

```bash
# From running app
python scripts/generate_api_docs.py --url http://localhost:8000 --update-nav

# From FastAPI import (CI / no server)
python scripts/generate_api_docs.py --import-app --cache --update-nav

# From cached file
python scripts/generate_api_docs.py --file openapi.json --update-nav

# Specific tags only
python scripts/generate_api_docs.py --import-app --tags patients,documents,dicom
```

**Output:** `docs/api/*.en.md` (English, MkDocs i18n suffix layout)

**Config:** `scripts/api_docs_config.py` · **CI:** `.github/workflows/docs-generate.yml`

Custom endpoint description in FastAPI:

```python
@router.post("/patients", openapi_extra={"x-docs": {"description": "Custom text."}})
```

Hide endpoint: `openapi_extra={"x-hide-docs": True}`

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
| POST | `/api/auth/register` | Регистрация (rate limit: 5/час) |
| POST | `/api/auth/login` | Вход, получение JWT (rate limit: 10/мин) |
| POST | `/api/auth/request-reset` | Запрос сброса пароля (rate limit: 3/час) |

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
| POST | `/api/analytics/predict-with-dicom/{patient_id}` | Прогноз с DICOM-контекстом (метаданные, находки, измерения) |
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
| `DATABASE_URL` | URL базы данных | `sqlite:///./medinsight.db` (dev) |
| `DEVELOPMENT_DATABASE_URL` | SQLite для локальной разработки | `sqlite:///./medinsight.db` |
| `PRODUCTION_DATABASE_URL` | PostgreSQL для production | `postgresql://…@postgres:5432/medinsight` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Учётные данные контейнера postgres | см. `.env.example` |
| `STORAGE_PATH` | Путь к файлам | `./storage` |
| `REDIS_URL` | Redis брокер Celery | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | Redis для результатов | `redis://redis:6379/1` |
| `OPENAI_API_KEY` | Ключ ProxyAPI/OpenAI | — |
| `OPENAI_BASE_URL` | Base URL ProxyAPI | `https://api.proxyapi.ru/openai/v1` |
| `OPENAI_MODEL` | Модель GPT | `gpt-4o-mini` |
| `SPACY_MODEL` | Модель spaCy | `ru_core_news_lg` |

## Роли

- `super_admin` — все клиники, управление системой
- `admin` — полный доступ в своей клинике
- `head_of_department` — все пациенты своего отделения
- `doctor` — свои пациенты + чтение пациентов своего отделения
- `nurse` — чтение пациентов своего отделения
- `researcher` — анонимизированные данные
- `viewer` — только просмотр

Подробнее — раздел «Разграничение доступа по отделениям».

## Лицензия

MIT

## Фаза 3: Multi-tenancy, RBAC, Encryption

### Мультитенантность

- Каждый пользователь принадлежит **Tenant** (клинике)
- Все данные изолированы по `tenant_id`
- **Super Admin** видит все tenant'ы
- Заголовок `X-Tenant-ID` или subdomain при входе

### RBAC — роли

| Роль | Права |
|------|-------|
| `super_admin` | Все tenant'ы, управление системой |
| `admin` | Полный доступ в своей клинике, пользователи, аудит |
| `head_of_department` | Все пациенты своего отделения (CRUD) |
| `doctor` | Свои пациенты (CRUD) + чтение пациентов своего отделения |
| `nurse` | Чтение пациентов своего отделения |
| `researcher` | Анонимизированные данные клиники |
| `viewer` | Только просмотр |

> Флаг `can_see_all_patients=true` у пользователя снимает ограничение по
> отделению — он видит всех пациентов клиники независимо от роли.

### Шифрование (age)

```bash
python scripts/generate_encryption_key.py
# Ключ: secrets/encryption_key.txt (не в git!)
```

- Файлы шифруются при загрузке → `storage/encrypted/tenant_{id}/patient_{id}/`
- Скачивание расшифровывает **в памяти** (не на диск)
- `ENCRYPTION_ENABLED=true` в `.env`

### Admin API

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/admin/tenants` | Создать клинику (super_admin) |
| GET | `/api/admin/tenants` | Список клиник |
| POST | `/api/admin/users` | Создать пользователя (с `department_id`, `can_see_all_patients`) |
| GET | `/api/admin/users` | Список пользователей |
| PUT | `/api/admin/users/{id}/role` | Изменить роль |
| POST | `/api/admin/users/{id}/block` | Деактивировать пользователя |
| POST | `/api/admin/users/{id}/unblock` | Активировать пользователя |
| DELETE | `/api/admin/users/{id}` | Удалить (записи переназначаются на админа) |
| POST/GET/PUT/DELETE | `/api/admin/departments` | Управление отделениями |
| GET | `/api/admin/audit` | Журнал аудита |
| GET | `/api/admin/health` | Системное здоровье |
| POST | `/api/admin/encryption/rotate` | Ротация ключа (super_admin) |

### Тест Фазы 3

```bash
pip install httpx python-docx pyrage
python scripts/test_tenant.py http://localhost:8000
```

Super Admin по умолчанию: `admin@medinsight.com` / `change_me_super_admin` (из `.env`).

### Переменные окружения (Фаза 3)

| Переменная | Описание |
|------------|----------|
| `TENANT_MODE` | Мультитенантность (true/false) |
| `ENCRYPTION_ENABLED` | Шифрование файлов |
| `ENCRYPTION_KEY` | age ключ (опционально) |
| `ENCRYPTION_KEY_PATH` | Путь к ключу (default: secrets/encryption_key.txt) |
| `SUPER_ADMIN_EMAIL` | Email суперадмина |
| `SUPER_ADMIN_PASSWORD` | Пароль суперадмина |

## Фаза 4: Self-Healing RAG + Вебхуки + Платежи

### Self-Healing RAG (самообучение)

Агенты `parser`, `extractor`, `predictor`, `summarizer` обёрнуты в декоратор
`@with_self_healing(...)`. При исключении система ищет похожие ошибки в базе
знаний и применяет известное решение (retry с backoff, context overlay,
fuzzy-matching), затем повторяет вызов.

- **Хранилище:** SQL-таблица `error_fixes` (durable) + ChromaDB как индекс
  семантической близости. Если `chromadb`/эмбеддинги недоступны — используется
  keyword-fallback (Jaccard-overlap), система продолжает работать.
- **Seed-fixes:** `app/services/self_healing/seed_fixes.json` загружаются на
  старте (типовые ошибки: ParserError, KeyError, OpenAI rate limit,
  UnicodeDecodeError).
- **Периодическое обучение:** Celery Beat `learn_from_failures` каждые 6 часов
  анализирует «застрявшие» ошибки и генерирует новые решения через GPT.

Admin API (super_admin):

```
GET    /api/admin/self-healing/stats
GET    /api/admin/self-healing/fixes
POST   /api/admin/self-healing/seed-fixes
POST   /api/admin/self-healing/confirm/{fix_id}
DELETE /api/admin/self-healing/fixes/{fix_id}
```

### Вебхуки

События: `analysis.completed`, `prediction.ready`, `patient.updated`.
Доставка подписывается `HMAC-SHA256` (заголовок `X-Webhook-Signature`),
3 повтора с экспоненциальной задержкой; после 5 сбоев вебхук авто-отключается.

```
POST   /api/webhooks/register
GET    /api/webhooks
PUT    /api/webhooks/{id}
DELETE /api/webhooks/{id}
POST   /api/webhooks/{id}/test
```

Проверка подписи получателем:

```python
import hmac, hashlib
expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, request.headers["X-Webhook-Signature"])
```

### Платежи (Stripe + ЮKassa)

Тарифы: **Freemium** (5 анализов/мес), **Pro** (100/мес, $19.99 / 1990 ₽),
**Enterprise** (без лимита, $99.99 / 9990 ₽). Лимит проверяется middleware
`UsageLimitMiddleware` перед каждым прогнозом — при превышении возвращается
`402 Payment Required`.

```
GET    /api/payments/prices
POST   /api/payments/create-checkout      # Stripe Checkout
POST   /api/payments/yookassa/create      # ЮKassa
GET    /api/payments/subscription
POST   /api/payments/cancel-subscription
POST   /webhooks/stripe                    # входящий, без auth (проверка подписи)
POST   /webhooks/yookassa                  # входящий, без auth
```

### Тест Фазы 4

```bash
python scripts/test_phase4.py
```

Проверяет: self-healing (искусственная ошибка → авто-фикс), вебхуки
(регистрация → событие → HMAC-доставка), платежи (лимиты Freemium → 402 →
апгрейд Pro).

### Переменные окружения (Фаза 4)

| Переменная | Описание |
|------------|----------|
| `SELF_HEALING_ENABLED` | Включить self-healing RAG |
| `CHROMA_PERSIST_DIR` | Каталог ChromaDB (default: ./chroma_data) |
| `SIMILARITY_THRESHOLD` | Порог близости для поиска фиксов (0.75) |
| `MAX_RETRY_ATTEMPTS` | Попыток применить фикс (2) |
| `WEBHOOK_ENABLED` | Включить отправку вебхуков |
| `WEBHOOK_RETRY_COUNT` | Повторов доставки (3) |
| `WEBHOOK_FAILURE_DEACTIVATE_THRESHOLD` | Сбоев до авто-отключения (5) |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Ключи Stripe |
| `STRIPE_PRICE_ID_PRO` / `STRIPE_PRICE_ID_ENTERPRISE` | ID цен Stripe |
| `YOOKASSA_SHOP_ID` / `YOOKASSA_SECRET_KEY` | Ключи ЮKassa |
| `FREEMIUM_ANALYSIS_LIMIT` / `PRO_ANALYSIS_LIMIT` / `ENTERPRISE_ANALYSIS_LIMIT` | Месячные лимиты |

> **ChromaDB опционален.** Пакет `chromadb` тянет `onnxruntime` (~200 МБ).
> Для лёгкого деплоя его можно закомментировать в `requirements.txt` —
> self-healing продолжит работать через SQL keyword-fallback.

## Разграничение доступа по отделениям

Доступ к пациентам ограничивается отделением (`Department`).

### Модель данных

```
TENANT 1—* DEPARTMENT 1—* USER
TENANT 1—* PATIENT *—1 DEPARTMENT
USER (attending_doctor_id) 1—* PATIENT
```

- **Department**: `id`, `tenant_id`, `name`, `head_doctor_id?`
- **User**: `+ department_id?`, `+ can_see_all_patients` (default `false`)
- **Patient**: `+ department_id` (обязателен при создании), `+ attending_doctor_id?`

### Правила видимости пациентов

| Роль | Что видит |
|------|-----------|
| `super_admin` | Все пациенты всех клиник |
| `admin` | Все пациенты своей клиники |
| `head_of_department` | Все пациенты своего отделения |
| `doctor` | Свои пациенты + все пациенты своего отделения (чтение) |
| `nurse` | Чтение пациентов своего отделения |
| `researcher` | Анонимизированные данные (без ПДн) |

Создавать/менять пациентов могут `super_admin`, `admin`, `head_of_department`,
`doctor`. Ограничение распространяется и на документы/прогнозы пациента, а
дашборд скоупится по доступным пациентам (есть фильтр `?department_id=`).

### Управление отделениями

```
POST   /api/admin/departments      # {"name": "...", "tenant_id"?, "head_doctor_id"?}
GET    /api/admin/departments
PUT    /api/admin/departments/{id}
DELETE /api/admin/departments/{id}  # пациенты/сотрудники открепляются
```

Создать стандартный набор отделений для тенанта:

```bash
docker compose exec app python scripts/seed_departments.py default
```

> При создании пациента **обязательно** указывать `department_id`. У сотрудников
> (`doctor`/`nurse`/`head_of_department`) задавайте `department_id`, иначе они
> не увидят пациентов отделения. Пациенты без отделения видны только админам.

## HTTPS (production)

В production трафик проксирует **Traefik** (порты 80/443) с автоматическим
сертификатом **Let's Encrypt** для `${DOMAIN}` и редиректом HTTP→HTTPS.

- Маршрутизация — через файловый провайдер `traefik/dynamic.yml` (без Docker
  socket: на новых демонах Traefik не согласует версию Docker API).
- Приложение слушает только `8000`; порты 80/443 занимает Traefik.
- В `.env` задайте `DOMAIN` и `ACME_EMAIL`.

```bash
./deploy.sh production   # поднимает app + redis + celery + traefik (профиль production)
```

Деплой автоматизирован через GitHub Actions (`.github/workflows/deploy.yml`):
push в `main` → тесты → SSH-деплой на VPS (`./deploy.sh production`).

## Мобильная адаптация

На экранах ≤768px навигация сворачивается в «гамбургер»-меню (выезжающая
панель со скрытыми страницами), таблицы получают горизонтальный скролл.

## Фаза 5: Production-ready (Healthchecks, Rate Limiting, Graceful Shutdown)

### Healthchecks

Эндпоинты для Docker/Kubernetes probe и мониторинга:

| Метод | Путь | Назначение | Коды ответа |
|-------|------|------------|-------------|
| GET | `/health` | Базовая проверка процесса | `200` `{"status":"ok","version":"1.0.0"}` |
| GET | `/health/live` | **Liveness** probe (жив ли процесс) | `200` `{"status":"alive"}` |
| GET | `/health/ready` | **Readiness** probe (готов ли принимать трафик) | `200` всё ОК / `503` есть проблема |
| GET | `/metrics` | Prometheus-метрики | `200` (text/plain) |

`/health/ready` проверяет зависимости и возвращает детали по каждой:

- **database** — `SELECT 1` (обязательная; падение → `503`)
- **redis** — `PING` (обязательная; падение → `503`)
- **celery** — `control.ping(timeout=2)` (опциональная; деградация, не `503`)
- **chromadb** — `list_collections()` если `SELF_HEALING_ENABLED=true` (опциональная)

Пример ответа `503`:

```json
{
  "status": "unavailable",
  "version": "1.0.0",
  "checks": {
    "database": {"ok": true, "detail": "ok", "required": true},
    "redis": {"ok": false, "detail": "ping failed", "required": true},
    "celery": {"ok": true, "detail": "1 worker(s)", "required": false}
  }
}
```

Docker healthcheck (в `docker-compose.yml` для сервиса `app`):

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

`celery_worker`, `celery_beat` и `traefik` стартуют только после того, как
`app` и `redis` стали `healthy` (`depends_on: condition: service_healthy`).

### Rate Limiting

Защита от брутфорса/DDoS через **sliding window counter** на Redis
(ключ `rate_limit:{ip}:{endpoint}`, sorted set с временными метками). При
превышении возвращается `429 Too Many Requests` с заголовком `Retry-After`.

| Эндпоинт | Лимит | Переменная |
|----------|-------|------------|
| `POST /api/auth/register` | 5 запросов / час | `RATE_LIMIT_REGISTER_PER_HOUR` |
| `POST /api/auth/login` | 10 запросов / минуту | `RATE_LIMIT_LOGIN_PER_MINUTE` |
| `POST /api/auth/request-reset` | 3 запроса / час | `RATE_LIMIT_RESET_PER_HOUR` |

- IP клиента определяется с учётом reverse-proxy (`X-Forwarded-For` / `X-Real-IP`).
- **Fail-open**: если Redis недоступен или `RATE_LIMIT_ENABLED=false`, запросы
  пропускаются — сбой инфраструктуры не блокирует пользователей.
- Декоратор многоразовый: `@rate_limit(limit=5, period=3600, name="...")`
  (handler должен принимать `request: Request`).
- Метрика `rate_limit_exceeded_total{endpoint, ip_hash}` инкрементируется при
  каждом отказе (IP хэшируется для приватности).

### Graceful Shutdown

При получении `SIGTERM` / `SIGINT` (`docker stop`, deploy, Ctrl+C) приложение
завершается аккуратно. Логика вынесена в `ShutdownManager`
(`app/core/shutdown.py`): обработчики выполняются последовательно, каждый со
своим таймаутом, сбой одного не прерывает остальные, вся цепочка защищена
`asyncio.shield`.

Порядок шагов (каждый логируется в консоль):

1. **drain_requests** — дождаться завершения текущих запросов
   (до `GRACEFUL_SHUTDOWN_TIMEOUT` сек, по умолчанию 30).
2. **revoke_celery_tasks** — отменить активные задачи Celery (`revoke(terminate=True)`).
3. **close_database** — `engine.dispose()`.
4. **close_redis** — закрыть пул соединений Redis.
5. **close_chromadb** — очистить системный кэш ChromaDB.
6. **close_executor** — `ThreadPoolExecutor.shutdown(wait=True)`.

Регистрация в `app/main.py` через `lifespan`; обработчик идемпотентен (повторный
вызов из lifespan/сигнала безопасен).

### Prometheus-метрики

Доступны на `GET /metrics` (no-op, если `prometheus-client` не установлен):

- `rate_limit_exceeded_total{endpoint, ip_hash}` — Counter отказов rate limiting.
- `health_status{component}` — Gauge готовности зависимости (`1`/`0`),
  компоненты: `database`, `redis`, `celery`, `chromadb`, `overall`.

### Тест Фазы 5

```bash
scripts/test_health.sh                  # локально (http://localhost:8000)
scripts/test_health.sh https://your-domain
```

Скрипт проверяет `/health`, `/health/live`, `/health/ready` и делает 11 запросов
к `/api/auth/login` — последний должен вернуть `429`.

### Переменные окружения (Фаза 5)

```env
RATE_LIMIT_ENABLED=true
RATE_LIMIT_LOGIN_PER_MINUTE=10
RATE_LIMIT_REGISTER_PER_HOUR=5
RATE_LIMIT_RESET_PER_HOUR=3
GRACEFUL_SHUTDOWN_TIMEOUT=30
APP_VERSION=1.0.0
```

## Фаза 7: Пагинация + экспорт в Excel

### Pagination

Универсальная пагинация/поиск/сортировка/фильтрация — `app/utils/pagination.py`
(`PaginationParams` + `paginate`). Списки возвращают конверт:

```json
{ "items": [...], "total": 95, "page": 1, "limit": 20, "pages": 5,
  "next_page": 2, "prev_page": null }
```

Общие query-параметры: `page` (≥1), `limit` (1..100), `search`, `sort_by`,
`sort_order` (`asc`|`desc`). Поиск/сортировка/фильтры применяются только к
реальным колонкам модели (защита от инъекций в `sort_by`/`filters`).

| Эндпоинт | Доп. параметры |
|----------|----------------|
| `GET /api/patients` | `search` (ФИО/тел/email), `department_id`, `attending_doctor_id` |
| `GET /api/documents` | `patient_id`, `document_type`, `status`, `search` |
| `GET /api/analytics/predictions` | `patient_id`, `type`, `validated` |
| `GET /api/admin/users` | `search` (email/ФИО), `role`, `is_active` |
| `GET /api/admin/departments` | `search` (название) |
| `GET /api/admin/audit` | `user_id`, `action`, `from_date`, `to_date` |

Для `admin/*` и `departments` сохранена обратная совместимость: без параметра
`page` возвращается простой массив (для старого UI и выпадающих списков); при
передаче `page` — пагинированный конверт.

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://medinsight.fileguardian.info/api/patients?page=2&limit=50&search=иванов&sort_by=last_name&sort_order=asc"
```

### Excel Export

Экспорт в `.xlsx` (`openpyxl`) — сервис `app/services/excel_export.py`
(`ExcelExporter`), эндпоинты `app/routes/export_excel.py`. Стиль: жирные
заголовки на фоне `#2563eb` белым, автоширина колонок, формат дат
`YYYY-MM-DD HH:MM:SS`, числа с 2 знаками, закрепление шапки.

| Эндпоинт | Доступ |
|----------|--------|
| `POST /api/export/patients` | can_export |
| `POST /api/export/documents` | can_export |
| `POST /api/export/predictions` | can_export |
| `POST /api/export/users` | admin |
| `POST /api/export/audit` | admin |
| `GET  /api/export/download/{job_id}` | авторизованный (для async) |

Тело: `{"filters": {...}, "columns": ["id", "full_name", ...]}` (пустой
`columns` → все колонки сущности). Имя файла: `{entity}_export_YYYY-MM-DD.xlsx`.

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"filters":{"department_id":1},"columns":["id","full_name","birth_date","email"]}' \
  -o patients.xlsx \
  https://medinsight.fileguardian.info/api/export/patients
```

**Большие выгрузки**: при числе строк > `EXPORT_MAX_ROWS` (по умолчанию 10000) и
доступном Redis экспорт уходит в Celery; эндпоинт отвечает JSON
`{"status":"processing","job_id":...,"download_url":"/api/export/download/<id>"}`,
файл сохраняется в `EXPORT_TEMP_DIR` (`storage/exports/`) и скачивается по
`download_url`, когда готов. Фронтенд (`dashboard.js`) опрашивает ссылку
автоматически.

Переменные окружения (Фаза 7):

```env
EXPORT_MAX_ROWS=10000
EXPORT_MAX_COLUMNS=50
EXPORT_TEMP_DIR=./storage/exports
```

Тест: `python scripts/test_export.py` (проверяет генерацию .xlsx и логику пагинации).

## Фаза 9: OpenTelemetry (трассировка) + WebSocket (real-time)

### OpenTelemetry (Distributed Tracing)

Распределённая трассировка через OpenTelemetry → OTLP (gRPC) → Collector → Jaeger.
Полностью **опциональна**: при `OTEL_ENABLED=false` или отсутствии пакетов — no-op.

Инструментируются: FastAPI (спан на запрос), SQLAlchemy (`db.statement`),
Redis, Celery (parent→child), HTTP-клиенты (requests/httpx), вызовы OpenAI
(`model`, `prompt_tokens`, `completion_tokens`, `total_tokens`). Агенты обёрнуты
в `@trace_span` (`app/utils/tracing.py`): `parser_agent`, `extractor_agent`,
`predictor_agent`, `summarizer_agent`.

Запуск стенда наблюдаемости (Jaeger UI + Collector) и включение трассировки:

```bash
# 1) поднять Jaeger + OTel Collector (profile observability)
docker compose --profile observability up -d jaeger otel-collector
# 2) включить в .env и перезапустить app/celery
#    OTEL_ENABLED=true
./deploy.sh production
# 3) Jaeger UI: http://<host>:16686  (service = medinsight)
```

Параметры (`.env`): `OTEL_ENABLED`, `OTEL_SERVICE_NAME`,
`OTEL_EXPORTER_OTLP_ENDPOINT` (по умолчанию `http://otel-collector:4317`),
`OTEL_TRACES_SAMPLER_ARG` (доля сэмплинга, 0.1 = 10%), `OTEL_DEPLOYMENT_ENVIRONMENT`.
Конфиг коллектора — `otel-collector-config.yml` (OTLP → Jaeger). Пропагация —
W3C Trace Context (`traceparent`).

Кастомный спан в своём коде:

```python
from app.utils.tracing import trace_span, add_span_attributes

@trace_span("my_op", {"agent": "custom"})
def do_work(...):
    add_span_attributes(patient_id=42)
    ...
```

### WebSocket (Real-time Notifications)

Мгновенные уведомления через WebSocket. Доставка между процессами
(Celery worker → API) идёт через Redis pub/sub: `publish_event(...)` публикует
конверт в канал, фоновый listener в API рассылает его нужным соединениям.

События: `prediction.ready`, `analysis.completed`, `limit.exceeded`,
`document.parsed`, `patient.updated`.

Подключение (JWT в query-параметре):

```
wss://medinsight.fileguardian.info/ws/<client_id>?token=<JWT>
```

Протокол (JSON):

```jsonc
// подписка / отписка
{"action":"subscribe","events":["prediction.ready","analysis.completed"]}
{"action":"unsubscribe","events":["prediction.ready"]}
{"action":"ping"}                      // → {"event":"pong"}
// сервер шлёт heartbeat каждые WEBSOCKET_HEARTBEAT_INTERVAL сек: {"event":"ping"}
```

Формат события:

```json
{
  "event": "prediction.ready",
  "data": {"patient_id": 42, "prediction_id": 123, "type": "readmission", "risk": 42, "confidence": 0.85},
  "timestamp": "2026-01-15T10:30:00Z",
  "user_id": 42, "tenant_id": 1, "department_id": null
}
```

Клиент: `static/websocket.js` (`MedInsightSocket`) — авто-reconnect с backoff,
heartbeat, тосты, индикатор `🟢/🔴` (элемент `#ws-status`):

```html
<script src="/static/websocket.js"></script>
<script>
  const sock = new MedInsightSocket({ onEvent: (e) => console.log('event', e) });
  sock.connect();
</script>
```

Безопасность: аутентификация по JWT; пользователь получает только события,
адресованные его `user_id` / `tenant_id` / `department_id`; глобальный лимит
соединений `WEBSOCKET_MAX_CONNECTIONS`. Параметры: `WEBSOCKET_ENABLED`,
`WEBSOCKET_HEARTBEAT_INTERVAL`, `WEBSOCKET_MAX_CONNECTIONS`, `WEBSOCKET_AUTH_TIMEOUT`.

Метрики (`/metrics`): `websocket_connections_total`,
`websocket_messages_sent_total`, `websocket_messages_received_total`,
`otel_spans_exported_total`, `otel_spans_dropped_total`.

Тест: `python scripts/test_websocket.py`.

## Фаза 10: Telegram Bot (уведомления)

Telegram-бот для push-уведомлений о событиях MedInsight: готовность прогноза,
завершение анализа документов, превышение лимитов, новый пациент. Модуль —
`app/bot/`, API привязки — `app/routes/telegram.py`.

### Подключение

1. Создайте бота через [@BotFather](https://t.me/BotFather), получите токен.
2. В `.env`:

```env
TELEGRAM_BOT_TOKEN=123456:ABCdef...
TELEGRAM_BOT_ENABLED=true
# опционально webhook вместо polling:
# TELEGRAM_BOT_WEBHOOK_URL=https://your-domain/telegram/webhook
# TELEGRAM_BOT_WEBHOOK_SECRET=random-secret
```

3. Запустите сервис бота:

```bash
docker compose up -d telegram_bot
# или локально:
python -m app.bot.main
```

### Привязка аккаунта

1. Пользователь отправляет боту `/start`.
2. Бот выдаёт **6-значный код** (действует 10 мин, хранится в Redis).
3. На сайте MedInsight (настройки профиля) пользователь вводит код:
   `POST /api/telegram/link` с телом `{"code": "123456"}` (JWT обязателен).
4. После привязки доступны команды `/menu`, `/settings`, `/status`.

### Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие, код привязки |
| `/menu` | Главное меню (inline-кнопки) |
| `/settings` | Включить/выключить типы уведомлений |
| `/subscribe` | Подписаться на все события |
| `/unsubscribe` | Отключить все уведомления |
| `/status` | Статус привязки и подписок |
| `/help` | Справка (MkDocs, предсобранный `site/` в репозитории) |

### API

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/telegram/link` | Привязать Telegram по коду |
| `GET` | `/api/telegram/status` | Статус привязки и подписок |
| `POST` | `/api/telegram/subscribe` | Обновить список событий |
| `DELETE` | `/api/telegram/link` | Отвязать Telegram |

События подписки: `prediction.ready`, `analysis.completed`, `limit.exceeded`,
`patient.created`.

### Интеграция

Уведомления отправляются из:

- `app/tasks/predict_task.py` — прогноз готов;
- `app/tasks/parse_task.py` — анализ документа завершён;
- `app/middleware/usage_limit.py` — лимит анализов превышен;
- `app/routes/patients.py` — новый пациент (если подписан).

Сервис отправки: `app/bot/services/notification_service.py`
(`TelegramNotificationService`). Fail-safe: ошибки Telegram не ломают основной
поток.

### Безопасность

- Привязка только через одноразовый код + авторизованный API-запрос.
- Токен бота **не логируется**.
- Rate limiting команд бота через Redis (`TELEGRAM_BOT_COMMAND_RATE_LIMIT`, по
  умолчанию 30/мин на пользователя).

Тот же `TELEGRAM_BOT_TOKEN` используется для алертов бэкапов (`TELEGRAM_CHAT_ID`
в Фазе 8) — это отдельный admin-чат, не пользовательские уведомления.

Тест: `python scripts/test_telegram_bot.py` (офлайн); live —
`python scripts/test_telegram_bot.py --send-test`.

## Фаза 11: Dark Mode (тёмная тема)

Полноценная светлая/тёмная тема через CSS-переменные (`static/styles/themes.css`).
Все страницы используют токены `--bg-*`, `--text-*`, `--accent-*` вместо
hardcoded цветов. Переключатель ☀️/🌙 — в хедере (или на странице входа).

### Переключение

1. Нажмите кнопку темы в navbar → переключение `light` ↔ `dark`.
2. Выбор сохраняется в `localStorage` (`theme`) и синхронизируется с БД:
   `PUT /api/preferences/theme` с телом `{"theme":"dark"}` (JWT).
3. При первом входе тема подгружается с сервера (`GET /api/preferences`).

Поддерживается режим **system** (следовать `prefers-color-scheme`) через API;
переключатель в UI циклично меняет light/dark.

### API

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/preferences` | Настройки пользователя |
| `PUT` | `/api/preferences` | Обновить theme и/или settings |
| `PUT` | `/api/preferences/theme` | Обновить только тему |

Значения `theme`: `light`, `dark`, `system`.

### Chart.js

Графики на дашборде автоматически перекрашиваются при событии `themechange`
(слушатель в `dashboard.js`, цвета из CSS-переменных `--chart-*`).

### Переменные окружения

```env
DEFAULT_THEME=light   # light | dark | system — для новых пользователей
```

Тест: `python scripts/test_theme.py`.

## Фаза 12: DICOM Support (медицинские изображения)

Загрузка, хранение, просмотр и анализ DICOM-файлов. Оригиналы шифруются через age
(как документы в Фазе 3); кадры конвертируются в PNG на сервере (`pydicom` + Pillow)
для веб-просмотра.

### Возможности

- Загрузка `.dcm` через API или UI (`/dicom`, drag & drop)
- Асинхронная обработка Celery (`process_dicom_study`)
- Веб-вьюер OHIF-style: `/dicom/viewer/{study_uid}` — серии, кадры, zoom/pan/rotate, W/L
- RBAC + изоляция по `tenant_id`; аудит upload/view/delete
- WebSocket (`dicom.ready`) + Telegram при завершении обработки
- Метаданные (модальность, body part) в аналитике дашборда

### API

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/dicom/upload` | multipart: `file`, `patient_id` → `{study_uid, job_id, status}` |
| `GET` | `/api/dicom/studies` | Список с пагинацией (фильтры: patient_id, modality, status, date_from/to) |
| `GET` | `/api/dicom/studies/{study_uid}` | Детали исследования (серии, кадры) |
| `GET` | `/api/dicom/studies/{study_uid}/series/{series_uid}/frames` | Кадры серии |
| `GET` | `/api/dicom/frames/{instance_uid}` | PNG-кадр (JWT, range-friendly) |
| `GET` | `/api/dicom/studies/{study_uid}/thumbnail` | Превью (первый кадр) |
| `DELETE` | `/api/dicom/studies/{study_uid}` | Удаление (admin) |
| `POST` | `/api/dicom/upload-zip` | multipart: `zip_file`, `patient_id` |
| `GET` | `/api/dicom/upload-zip/status/{job_id}` | Прогресс обработки ZIP |
| `GET` | `/api/dicom/studies/{study_uid}/archive` | Скачать оригинальный ZIP |

```bash
TOKEN=...  # JWT врача
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -F "patient_id=1" -F "file=@scan.dcm" \
  https://medinsight.fileguardian.info/api/dicom/upload
```

### Хранение

```
storage/dicom/{patient_id}/{study_uid}/frames/{instance_uid}_f{N}.png
storage/encrypted/tenant_{id}/patient_{id}/dicom_{study_uid}_*.age  # оригинал
```

### Переменные окружения

```env
DICOM_ENABLED=true
DICOM_MAX_FILE_SIZE_MB=500
DICOM_STORAGE_PATH=./storage/dicom
DICOM_THUMBNAIL_SIZE=256x256
```

### UI

- `/dicom` — список исследований, фильтры, загрузка
- `/dicom/viewer/{study_uid}` — просмотр (canvas, навигация по кадрам)

Тест: `python scripts/test_dicom.py` (синтетический DICOM + парсинг + БД).

### DICOM ZIP / 7z Support

Загрузка **ZIP или 7z архивов** с множеством `.dcm` файлов (стандартный экспорт с КТ/МРТ).

- `POST /api/dicom/upload-zip` — multipart: `zip_file` (`.zip` или `.7z`), `patient_id`
- `GET /api/dicom/upload-zip/status/{job_id}?study_id=` — прогресс обработки
- `GET /api/dicom/studies/{study_uid}/archive` — скачать оригинальный ZIP (зашифрован на диске)
- Celery: `process_dicom_zip` (таймаут 30 мин, прогресс каждые 100 файлов)
- Группировка по Study/Series UID; защита от zip-бомб (лимит файлов и размера)

```env
DICOM_ZIP_MAX_SIZE_MB=2048
DICOM_ZIP_TEMP_DIR=./temp/dicom_zip
DICOM_ZIP_MAX_FILES=5000
DICOM_ZIP_TASK_TIMEOUT_SEC=1800
```

Тест: `python scripts/test_dicom_zip.py`

### DICOM Annotations (разметка изображений)

Рисование аннотаций поверх DICOM-кадров: прямоугольники, круги, стрелки, текст, линии,
измерения расстояния и углов. Аннотации сохраняются в БД (JSON) и подгружаются при
повторном открытии кадра.

#### Возможности

- Инструменты: rectangle, circle, arrow, text, line, measurement, angle
- Auto-save через 500 ms после изменения (настраивается)
- Canvas overlay в вьюере и на отдельной странице аннотаций
- Экспорт JSON / GeoJSON; импорт JSON
- RBAC: доступ только к пациентам, видимым пользователю; аудит create/update/delete
- Сессии аннотаций (последний открытый кадр)

#### API

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/dicom/annotations` | Создать аннотацию |
| `GET` | `/api/dicom/annotations/frame/{frame_id}` | Список по frame_id |
| `GET` | `/api/dicom/annotations/frame-instance/{uid}` | Список по instance UID |
| `PUT` | `/api/dicom/annotations/{id}` | Обновить |
| `DELETE` | `/api/dicom/annotations/{id}` | Удалить (soft) |
| `DELETE` | `/api/dicom/annotations/frame/{frame_id}` | Удалить все на кадре |
| `POST` | `/api/dicom/annotations/export/{frame_id}` | Экспорт JSON |
| `GET` | `/api/dicom/annotations/export/{frame_id}/geojson` | Экспорт GeoJSON |
| `POST` | `/api/dicom/annotations/import/{frame_id}` | Импорт JSON |
| `GET` | `/api/dicom/annotations/session` | Текущая сессия |
| `POST` | `/api/dicom/annotations/session` | Начать сессию |
| `GET` | `/api/dicom/annotations/config` | Настройки (enabled, delay, max) |

#### Annotation Editing (Phase 12d)

- Режимы: **Select**, **Move**, **Resize** + инструменты рисования
- Маркеры на выделенной аннотации (углы, центр, радиус)
- Двойной клик → попап (label, color, type)
- Горячие клавиши: `Delete`, `Ctrl+Z`, `Ctrl+Y`
- API: `PUT .../move`, `.../resize`, `.../color`, `.../label`, `.../type`
- История правок в `annotation_history` (undo/audit)

#### Annotation Export (JSON, GeoJSON, PDF)

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/dicom/annotations/export/json/{frame_id}` | Стандартизированный JSON v1.0 |
| `POST` | `/api/dicom/annotations/export/json` | JSON для нескольких кадров |
| `GET` | `/api/dicom/annotations/export/geojson/{frame_id}` | GeoJSON FeatureCollection |
| `GET` | `/api/dicom/annotations/export/pdf/{frame_id}` | PDF A4 с изображением и легендой |
| `POST` | `/api/dicom/annotations/export/pdf` | PDF с опциями |
| `POST` | `/api/dicom/annotations/export/batch` | ZIP (json/geojson/pdf) |
| `POST` | `/api/dicom/annotations/import/geojson/{frame_id}` | Импорт GeoJSON |

```env
DICOM_ANNOTATIONS_HISTORY_LIMIT=50
DICOM_ANNOTATIONS_EXPORT_MAX_FRAMES=100
```

Тесты: `python scripts/test_annotations.py`, `python scripts/test_annotation_export.py`

#### UI (редактор)

- `/dicom/annotate/{study_uid}/{series_uid}/{frame_instance_uid}` — редактор с экспортом
- `/dicom/annotate-edit/{study_uid}/{series_uid}/{frame_instance_uid}` — полный редактор

```env
DICOM_ANNOTATIONS_ENABLED=true
DICOM_ANNOTATIONS_AUTO_SAVE_DELAY_MS=500
DICOM_ANNOTATIONS_MAX_PER_FRAME=100
```

Тест: `python scripts/test_annotations.py`

### 3D Volume Rendering (объёмная реконструкция)

Просмотр DICOM-исследований в 3D: Volume Rendering (VR), Multiplanar Reconstruction (MPR),
Maximum Intensity Projection (MIP), пресеты Window/Level (Bone, Lung, Brain, Abdomen, Liver).

**Стек:** Cornerstone3D + vtk.js (frontend), numpy/scipy (backend), Redis-кэш объёмов.

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/api/dicom/volume/{study_uid}/info` | Метаданные объёма (размеры, spacing, статус кэша) |
| `GET` | `/api/dicom/volume/{study_uid}/render` | 3D-проекция (PNG): `preset`, `mode`, `azimuth`, `elevation` |
| `GET` | `/api/dicom/volume/{study_uid}/mpr/{plane}/{slice}` | MPR-срез (`axial` / `coronal` / `sagittal`) |
| `POST` | `/api/dicom/volume/{study_uid}/reconstruct` | Асинхронная сборка объёма (Celery) |

**UI:** `/dicom/3d/{study_uid}` — полноэкранный 3D-вьюер (VR слева, три MPR справа, toolbar снизу).
Кнопка «3D» доступна в 2D-вьюере `/dicom/viewer/{study_uid}`.

```env
DICOM_3D_ENABLED=true
DICOM_3D_CACHE_SIZE_GB=10
DICOM_3D_MAX_VOLUME_MB=2048
DICOM_3D_RENDER_TIMEOUT_SECONDS=30
DICOM_3D_CACHE_TTL_SECONDS=3600
```

Кэш Redis: `volume:{study_uid}:data` (бинарный объём), `volume:{study_uid}:info` (JSON).
Fallback на диск: `{DICOM_STORAGE_PATH}/{patient_id}/{study_uid}/volume/`.

Тест: `python scripts/test_3d_render.py`

### DICOM + AI Predictions (интеграция метаданных в GPT-прогнозы)

Серверный пайплайн извлекает из DICOM-исследований метаданные, измерения (аннотации),
находки и заключения, формирует структурированный клинический контекст и передаёт его
в GPT вместе с данными документов и лабораторными показателями.

**Сервисы:**
- `app/services/dicom_text_extractor.py` — метаданные, SR-текст, сборка контекста
- `app/services/dicom_measurement_extractor.py` — органы, опухоли, кости, сосуды
- `app/services/dicom_radiology_parser.py` — находки, impression, рекомендации
- `app/services/dicom_rag.py` — индексация контекста в ChromaDB (семантический поиск)
- `app/prompts/dicom_prompts.py` — шаблоны промптов и клинические рекомендации по модальностям

**API:**

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/dicom/study/{study_uid}/clinical-context` | Структурированный клинический контекст |
| `POST` | `/api/dicom/study/{study_uid}/process` | Извлечение метаданных, находок, измерений |
| `POST` | `/api/analytics/predict-with-dicom/{patient_id}` | Прогноз с учётом DICOM + источники |

Обычный `POST /api/analytics/predict/{id}` также автоматически включает DICOM-данные,
если у пациента есть готовые исследования (`status=ready`).

**Поля `DicomStudy`:** `radiology_findings`, `radiology_impression`, `extracted_measurements`,
`clinical_context`, `clinical_context_processed_at`.

```env
DICOM_RAG_ENABLED=true
DICOM_RAG_CHUNK_SIZE=512
DICOM_RAG_OVERLAP=50
```

Тест: `python scripts/test_dicom_context.py`

## Фаза 8: Резервное копирование (Backup & Restore)

Автоматический и ручной бэкап БД (SQLite) и `storage/`, восстановление и ротация.
Сервис — `app/services/backup.py` (`BackupService`), задачи Celery —
`app/tasks/backup_task.py`, API — `app/routes/admin_backup.py` (только super_admin).

### Что и куда

```
/backups/
├── full/       backup_<ts>.tar.gz          # БД + storage + config (.env без секретов) + metadata
├── db/         backup_<ts>.db.gz           # только БД (sqlite .backup + gzip)
├── storage/    backup_<ts>.storage.tar.gz  # только файлы
└── metadata/   backup_<ts>.json            # версия, размеры, sha256-чек-суммы
```

В Docker `/backups` — отдельный volume `medinsight-backups`. БД копируется через
`sqlite3 .backup` (консистентно, без блокировки). `.env` в full-бэкапе
**санитизируется** (значения с `KEY/PASSWORD/SECRET/TOKEN` → `__REDACTED__`).
Опциональное шифрование age-passphrase (`BACKUP_ENCRYPTION_ENABLED`).

### API (super_admin)

| Метод | Путь | Назначение |
|-------|------|------------|
| POST | `/api/admin/backup/create` | `{"type":"full\|db\|storage"}` → job_id |
| GET | `/api/admin/backup/status/{job_id}` | статус Celery-задачи |
| GET | `/api/admin/backup/list` | список бэкапов |
| GET | `/api/admin/backup/download/{backup_id}` | скачать `.tar.gz`/`.db.gz` |
| POST | `/api/admin/backup/restore` | `{"backup_id","type","confirm":true}` |
| DELETE | `/api/admin/backup/{backup_id}` | удалить бэкап |

```bash
TOKEN=...  # super_admin JWT
# создать полный бэкап
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"type":"full"}' https://medinsight.fileguardian.info/api/admin/backup/create
# список
curl -H "Authorization: Bearer $TOKEN" https://medinsight.fileguardian.info/api/admin/backup/list
# восстановление (требует confirm=true!)
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"backup_id":"backup_2026-01-15_02-00-00","type":"full","confirm":true}' \
  https://medinsight.fileguardian.info/api/admin/backup/restore
```

### Периодические задачи (Celery Beat)

При `BACKUP_ENABLED=true` регистрируются (cron из `.env`):

- `backup-full-daily` — `BACKUP_SCHEDULE_FULL` (по умолчанию 02:00)
- `backup-db-hourly` — `BACKUP_SCHEDULE_DB` (каждый час)
- `backup-cleanup-daily` — `BACKUP_SCHEDULE_CLEANUP` (03:00) — ротация GFS:
  `BACKUP_RETENTION_DAYS` ежедневных + `_WEEKS` еженедельных + `_MONTHS` месячных.

### Ручной бэкап / восстановление (без приложения)

```bash
./scripts/backup.sh full           # или db | storage  → в $BACKUP_DIR
./scripts/restore.sh /backups/full/backup_<ts>.tar.gz   # остановит и перезапустит контейнеры
```

### Мониторинг

Метрики Prometheus на `/metrics`: `backup_size_bytes{type}`,
`backup_duration_seconds{type}`, `backup_status_total{type,result}`,
`backup_age_days`. Алерты (лог + опционально Telegram через `TELEGRAM_BOT_TOKEN`/
`TELEGRAM_CHAT_ID`): последний бэкап старше `BACKUP_ALERT_MAX_AGE_HOURS` (48ч),
размер > `BACKUP_MAX_SIZE_MB`, восстановление > 5 мин.

### Безопасность
- Доступ к бэкапам — только `super_admin`; все действия пишутся в аудит.
- Секреты не попадают в архив (`.env` санитизируется).
- Перед восстановлением создаётся защитная копия (`*.pre-restore`); full-restore
  проверяет sha256 БД из `metadata.json`. Распаковка защищена от path traversal.

Переменные окружения (Фаза 8): см. `.env.example` (`BACKUP_*`, `TELEGRAM_*`).
Тест: `python scripts/test_backup.py`.

## Отключение биллинга (тестовый режим)

Главный выключатель `BILLING_ENABLED` (по образцу ReportAgent) позволяет
полностью отключить тарифные ограничения для тестирования/обслуживания.

```env
# .env
BILLING_ENABLED=false
```

При `BILLING_ENABLED=false`:

- лимиты анализов **не проверяются** — `UsageLimitMiddleware` пропускает все
  запросы, `POST /api/analytics/predict/{id}` не упирается в `402`;
- использование не инкрементируется (`increment_usage` → no-op);
- `GET /api/payments/subscription` возвращает `status: "testing"` и
  безлимитную квоту (`999999`);
- `GET /api/payments/prices` содержит `"billing_enabled": false`;
- оплата (`create-checkout`, `yookassa/create`) отвечает `503 Billing is disabled`.

Логика вынесена в `app/services/payment/billing_config.py`
(`billing_enabled()`, `stripe_checkout_enabled()`, `yookassa_checkout_enabled()`).
Чтобы применить — поменяйте `BILLING_ENABLED` в `.env` и пересоберите
(`./deploy.sh` / GitHub Actions).

## Фаза 6: Email-уведомления + JSON-логи

### Email Notifications

Асинхронная отправка писем через SMTP (`aiosmtplib`) с HTML + plain-text
шаблонами (`app/templates/email/`). Сервис — `app/services/email.py`
(`EmailService`). Отправка всегда **fail-safe**: при ошибке пишется лог, но
запрос/задача не падают. Если `EMAIL_ENABLED=false` или не задан `SMTP_HOST` —
отправка тихо пропускается.

| Событие | Метод | Когда |
|---------|-------|-------|
| Подтверждение регистрации | `send_verification_email` | `POST /api/auth/register` |
| Сброс пароля | `send_password_reset_email` | `POST /api/auth/request-reset` |
| Прогноз готов | `send_prediction_ready_email` | после `POST /api/analytics/predict/{id}` (sync и Celery) |
| Превышение лимита | `send_limit_exceeded_email` | `UsageLimitMiddleware` при `402` (раз в 24ч на тенант) |

Письма из HTTP-эндпоинтов отправляются через `BackgroundTasks` (после ответа),
из Celery-воркера — синхронно через `asyncio.run`. Ссылки строятся от
`FRONTEND_URL`. Токены верификации/сброса — подписанные JWT с TTL
(`EMAIL_VERIFICATION_EXPIRE_HOURS`, `EMAIL_PASSWORD_RESET_EXPIRE_HOURS`).

Настройка (`.env`), для Gmail используйте App Password:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@medinsight.com
EMAIL_ENABLED=true
FRONTEND_URL=https://medinsight.fileguardian.info
```

Тест (рендер всех шаблонов + проверка JSON-логов; с `--to` — реальная отправка):

```bash
python scripts/test_email.py
python scripts/test_email.py --to you@example.com
```

### Logging (структурированные JSON-логи)

Логирование настроено через **structlog** (`app/utils/logging.py`) и
охватывает как сам код, так и библиотеки (uvicorn, sqlalchemy, celery) — всё
идёт одним пайплайном:

- `LOG_JSON_FORMAT=true` — одна JSON-строка на событие (для ELK / Loki).
- `LOG_JSON_FORMAT=false` — цветной человекочитаемый вывод (для разработки).

`LoggingMiddleware` (`app/middleware/logging.py`) на каждый запрос:

- присваивает/пробрасывает `X-Request-ID` (correlation id);
- через `contextvars` (`app/utils/request_context.py`) добавляет в каждый лог
  `request_id`, `user_id`, `tenant_id`, `ip`, `user_agent`;
- пишет строку `Request completed` с `method`, `path`, `status_code`,
  `duration_ms`, `response_size`;
- ошибки логирует с полным stack trace.

Медленные SQL-запросы (> `LOG_SLOW_QUERY_MS`, мс) логируются отдельно
(`app.database.sql`).

Успешные пробы (`/health*`, `/metrics`, `/favicon.ico`) **не логируются**, чтобы
не зашумлять логи healthcheck'ами Docker/K8s — при этом им всё равно
присваивается `request_id` и возвращается заголовок `X-Request-ID`. Ответы
`4xx/5xx` на этих путях логируются всегда (чтобы реальные проблемы были видны).

Пример строки лога (JSON):

```json
{
  "timestamp": "2026-01-15T10:30:00.123456Z",
  "level": "info",
  "logger": "app.middleware.logging",
  "request_id": "abc-123-def-456",
  "user_id": 42,
  "tenant_id": 1,
  "ip": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "method": "POST",
  "path": "/api/patients",
  "status_code": 201,
  "duration_ms": 45,
  "message": "Request completed"
}
```

Как читать логи в Docker:

```bash
# «сырые» JSON-логи
docker compose logs -f app

# красиво через jq (фильтр по конкретному request_id)
docker compose logs -f app | jq -c 'select(.request_id=="abc-123-def-456")'

# только ошибки
docker compose logs app | jq 'select(.level=="error")'
```

Переменные окружения (Фаза 6):

```env
LOG_LEVEL=INFO
LOG_JSON_FORMAT=true
LOG_INCLUDE_REQUEST_ID=true
LOG_INCLUDE_USER_ID=true
LOG_SLOW_QUERY_MS=500
```

## SIEM Integration (Фаза 13: Audit Export)

MedInsight экспортирует аудит-события во внешние SIEM-системы с криптографической
подписью (HMAC-SHA256), append-only хранением и гарантированной доставкой через
Celery retry.

### Поддерживаемые форматы и цели

| Формат | Протокол | Целевые SIEM |
|--------|----------|--------------|
| `syslog` | RFC 5424, TLS 1.2+ | Microsoft Sentinel, Securonix |
| `cef` | ArcSight CEF | ManageEngine Log360 |
| `splunk_hec` | Splunk HEC (HTTPS) | Splunk Enterprise/Cloud |
| `jsonl` | JSON Lines (локальный архив + экспорт) | Универсальный |

### Архитектура

```
Audit Collector → PostgreSQL (audit_logs) + подпись SHA-256
       ↓
Audit Exporter (Celery) → Syslog / CEF / HEC / JSONL
       ↓
Splunk | Sentinel | Log360 | Securonix
```

### Переменные окружения

```env
SIEM_EXPORT_ENABLED=true
SIEM_EXPORT_PROTOCOL=syslog
SIEM_EXPORT_HOST=siem.internal
SIEM_EXPORT_PORT=6514
SIEM_EXPORT_TLS=true
SIEM_EXPORT_RETRY_COUNT=3
SIEM_EXPORT_BATCH_SIZE=1000

# Splunk HEC
SPLUNK_HEC_URL=https://splunk.internal:8088/services/collector
SPLUNK_HEC_TOKEN=your-hec-token

# CEF
SIEM_EXPORT_CEF_VENDOR=MedInsight
SIEM_EXPORT_CEF_PRODUCT=ClinicalAnalytics

# TLS client cert (опционально)
SIEM_EXPORT_TLS_CERT=/path/to/cert.pem
SIEM_EXPORT_TLS_KEY=/path/to/key.pem

# Подпись событий
AUDIT_SIGNING_ENABLED=true
AUDIT_SIGNING_KEY_PATH=./secrets/audit_key.pem
```

### API (admin)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/admin/audit/export/status` | Статус экспорта и цели |
| POST | `/api/admin/audit/export/retry` | Повторная отправка |
| POST | `/api/admin/audit/export/test` | Тестовое событие |
| GET | `/api/admin/audit/export/events` | Список событий экспорта |
| GET | `/api/admin/audit/export/stats` | Статистика |

### Celery Beat

При `SIEM_EXPORT_ENABLED=true` задача `sync_pending_audit_events` запускается
каждые 5 минут и отправляет события со статусом `pending`.

### Тестирование

```bash
# Форматирование без отправки
python scripts/test_siem_export.py --format cef

# Отправка в SIEM (jsonl пишет локальный архив)
python scripts/test_siem_export.py --format jsonl --send

# Syslog / Splunk HEC (нужен доступный хост)
python scripts/test_siem_export.py --format syslog --target sentinel --send
```

### Безопасность

- Все каналы экспорта используют TLS 1.2+ (syslog over TLS, Splunk HEC HTTPS).
- События подписываются HMAC-SHA256; ключ хранится в `secrets/audit_key.pem`.
- PII обезличивается при экспорте (IP, email, телефоны в `details`).
- Таблица `audit_logs` защищена append-only триггером (PostgreSQL) и ORM-слушателями.
- Каждая попытка экспорта записывается в `audit_export_logs`.

### Миграции

- `021_add_audit_signing.sql` — колонки подписи и статуса экспорта
- `022_add_audit_export_tables.sql` — `audit_export_logs`, `audit_keys`
- `023_add_audit_append_only_trigger.sql` — PostgreSQL append-only trigger

## FHIR Integration (Фаза 14: HL7 FHIR Import/Export)

MedInsight поддерживает импорт и экспорт клинических данных в формате **HL7 FHIR R4/R4B**
(пакет `fhir.resources` 7.x, pydantic v2). FHIR REST API реализован на FastAPI.

### Поддерживаемые ресурсы

| MedInsight | FHIR Resource |
|------------|---------------|
| Patient | `Patient` |
| Document | `DiagnosticReport` + `Encounter` |
| Prediction | `Observation` |
| DicomStudy | `ImagingStudy` |

### Архитектура

```
MedInsight DB → FhirMapper → FHIR Resources
                    ↓
         FHIRStarter API (/fhir/*)
         REST Export/Import (/api/fhir/*)
                    ↓
         EHR (EPIC, Cerner) via SMART on FHIR
```

### FHIR REST API

При `FHIR_ENABLED=true` доступен FHIR REST API на `/fhir`:

| Endpoint | Описание |
|----------|----------|
| `GET /fhir/metadata` | CapabilityStatement |
| `GET /fhir/Patient/{id}` | Чтение пациента |
| `GET /fhir/Patient?family=&given=` | Поиск пациентов |
| `POST /fhir/Patient` | Создание пациента |
| `GET /fhir/Observation?patient=` | Прогнозы как Observation |
| `GET /fhir/DiagnosticReport?patient=` | Документы |
| `GET /fhir/ImagingStudy?patient=` | DICOM-исследования |
| `GET /fhir/Encounter?patient=` | Встречи/документы |

### MedInsight REST API

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/fhir/export/patient/{id}` | Bundle пациента |
| GET | `/api/fhir/export/tenant/{tenant_id}` | Все пациенты тенанта |
| GET | `/api/fhir/export/dicom/{study_uid}` | ImagingStudy |
| POST | `/api/fhir/export/batch` | Экспорт по дате/типу |
| POST | `/api/fhir/import/bundle` | Импорт Bundle |
| POST | `/api/fhir/import/patient` | Импорт Patient |
| POST | `/api/fhir/import/from-ehr` | Импорт из EHR (SMART) |

### Переменные окружения

```env
FHIR_ENABLED=true
FHIR_VERSION=R4
FHIR_BASE_URL=https://medinsight.com/fhir
FHIR_PUBLISHER=MedInsight

# SMART on FHIR (EPIC, Cerner)
SMART_ENABLED=false
SMART_AUTHORIZATION_URL=https://ehr.example.com/auth
SMART_TOKEN_URL=https://ehr.example.com/token
SMART_CLIENT_ID=client_id
SMART_CLIENT_SECRET=client_secret

FHIR_EXPORT_BATCH_SIZE=1000
FHIR_EXPORT_MAX_RESOURCES=10000
```

### Celery

- `export_fhir_batch` — асинхронный batch-экспорт в JSON-файл
- `export_to_external_ehr` — push Bundle во внешнюю EHR

### Тестирование

```bash
python scripts/test_fhir.py
```

### Миграции

- `025_add_fhir_mapping.sql` — таблица `fhir_mapping` (MedInsight ID ↔ FHIR ID)

## Report Templates (Фаза 15: PDF-отчёты)

Система шаблонов для генерации PDF-отчётов: клинические выписки, лабораторные
результаты, DICOM-отчёты, прогнозы рисков и полный клинический обзор.

### Архитектура

```
MedInsight Data → Jinja2 HTML шаблон → xhtml2pdf → PDF (ReportLab post-processing)
```

### Встроенные шаблоны

| Тип | Файл | Описание |
|-----|------|----------|
| `clinical` | `clinical.jinja2` | Клиническая выписка |
| `laboratory` | `laboratory.jinja2` | Результаты анализов |
| `dicom` | `dicom.jinja2` | DICOM-отчёт с изображениями |
| `prediction` | `prediction.jinja2` | Прогноз рисков (GPT) |
| `full` | `full.jinja2` | Полный клинический обзор |

При первом запросе `GET /api/templates` шаблоны автоматически создаются для тенанта.

### API

**Шаблоны**

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/templates` | Список шаблонов |
| GET | `/api/templates/{id}` | Получить шаблон |
| POST | `/api/templates` | Создать (admin) |
| PUT | `/api/templates/{id}` | Обновить (admin) |
| DELETE | `/api/templates/{id}` | Удалить (admin) |
| POST | `/api/templates/{id}/duplicate` | Дублировать |

**Отчёты**

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/api/reports/generate` | Сгенерировать PDF (Celery) |
| POST | `/api/reports/preview` | HTML-предпросмотр |
| GET | `/api/reports/{id}` | Статус отчёта |
| GET | `/api/reports/{id}/pdf` | Скачать PDF |
| GET | `/api/reports` | Список отчётов |
| DELETE | `/api/reports/{id}` | Удалить |

Пример генерации:

```bash
curl -X POST /api/reports/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"template_id": 1, "patient_id": 42}'
```

### Переменные окружения

```env
REPORTS_STORAGE_PATH=./storage/reports
REPORTS_MAX_FILE_SIZE_MB=50
REPORTS_TEMPLATES_DIR=./app/templates/reports
```

### Тестирование

```bash
python scripts/test_report_template.py
```

### Миграции

- `026_add_report_templates.sql` — `report_templates`, `report_template_variables`, `generated_reports`
