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
