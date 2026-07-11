# Конфигурация

Все настройки — через переменные окружения (`.env` или `.env.production`).

## Обязательные

| Переменная | Описание | Пример |
|------------|----------|--------|
| `SECRET_KEY` | JWT и криптография (≥32 символа) | `openssl rand -hex 32` |
| `DATABASE_URL` | SQLite или PostgreSQL | `sqlite:///./medinsight.db` |
| `REDIS_URL` | Брокер Celery и кэш | `redis://redis:6379/0` |

## Приложение

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `ENVIRONMENT` | `development` | `development` / `production` |
| `APP_PORT` | `8000` | Порт uvicorn |
| `APP_VERSION` | `1.0.0` | Версия в `/health` |
| `CORS_ORIGINS` | `*` | Разрешённые origins (через запятую) |
| `LOG_LEVEL` | `INFO` | Уровень логов |

## Безопасность и шифрование

| Переменная | Описание |
|------------|----------|
| `ENVIRONMENT` | `development` или `production` (fail-fast на дефолтных секретах в prod) |
| `AGE_PUBLIC_KEY` | Публичный ключ age для шифрования файлов |
| `AGE_SECRET_KEY` | Приватный ключ (только на сервере!) |
| `ENCRYPTION_ENABLED` | `true` / `false` |
| `MFA_ENFORCED` | `true` — требовать 2FA; `false` — временно отключить (см. ниже) |
| `MFA_REQUIRED_ROLES` | Роли, для которых обязателен TOTP (`admin,doctor` по умолчанию) |
| `PASSWORD_MIN_LENGTH` | Мин. длина пароля (12) |
| `LOGIN_LOCKOUT_MAX_ATTEMPTS` | Попыток до блокировки аккаунта (5) |

### 2FA (TOTP)

Пользователь включает TOTP в настройках аккаунта (`/api/totp/*`). При входе API может вернуть
`totp_required: true` — тогда повторите `POST /api/auth/login` с полем `totp_code`.

Временное отключение 2FA на сервере:

```bash
# в .env на VPS
MFA_ENFORCED=false
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate app celery_worker
```

!!! note
    `docker restart` не подхватывает новые переменные из `.env` — нужен `--force-recreate`
    или полный `./deploy.sh production`.

Генерация ключей:

```bash
age-keygen -o age-key.txt
# AGE_PUBLIC_KEY = age1...
# AGE_SECRET_KEY = AGE-SECRET-KEY-1...
```

## GPT / ProxyAPI

| Переменная | Описание |
|------------|----------|
| `PROXYAPI_KEY` | Ключ ProxyAPI (OpenAI-совместимый) |
| `PROXYAPI_BASE_URL` | Базовый URL API |
| `GPT_MODEL` | Модель, напр. `gpt-4o-mini` |

Без ключа работает rule-based fallback.

## Email (SMTP)

| Переменная | Описание |
|------------|----------|
| `SMTP_HOST`, `SMTP_PORT` | Сервер SMTP |
| `SMTP_USER`, `SMTP_PASSWORD` | Учётные данные |
| `SMTP_FROM` | Адрес отправителя |
| `FRONTEND_URL` | Базовый URL для ссылок в письмах |

## Telegram

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен @BotFather |
| `TELEGRAM_WEBHOOK_SECRET` | Секрет вебхука |

## DICOM

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DICOM_MAX_FILE_SIZE_MB` | `500` | Лимит загрузки |
| `DICOM_STORAGE_PATH` | `storage/dicom` | Каталог хранения |

## Резервное копирование

| Переменная | Описание |
|------------|----------|
| `BACKUP_ENABLED` | `true` / `false` |
| `BACKUP_SCHEDULE_CRON` | Расписание (Celery Beat) |
| `BACKUP_RETENTION_DAYS` | Срок хранения архивов |

## Мультитенантность

| Переменная | Описание |
|------------|----------|
| `DEFAULT_TENANT_SUBDOMAIN` | Subdomain по умолчанию |
| `TENANT_HEADER` | Заголовок для API (опционально) |

## Celery

| Переменная | Описание |
|------------|----------|
| `CELERY_BROKER_URL` | Обычно = `REDIS_URL` |
| `CELERY_RESULT_BACKEND` | Backend результатов |

## Применение изменений

Переменные из `.env` передаются в контейнер через `env_file` при **создании** контейнера.

```bash
# Недостаточно — старые env останутся в контейнере:
docker compose restart app

# Правильно — пересоздать app и worker:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate app celery_worker

# Или полный деплой (рекомендуется):
./deploy.sh production
```

Добавить недостающие ключи из `.env.example` без потери секретов:

```bash
python scripts/sync_env_from_example.py
```

Полный список: [environment-variables.md](../deployment/environment-variables.md).
