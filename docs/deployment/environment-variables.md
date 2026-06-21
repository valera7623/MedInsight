# Переменные окружения

Полный справочник переменных из `.env.example`.

## Безопасность и JWT

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SECRET_KEY` | — | Секрет JWT (≥32 символа). **Обязательно** |
| `ALGORITHM` | `HS256` | Алгоритм JWT |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | Срок жизни токена |

## База данных и хранилище

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATABASE_URL` | `sqlite:///./medinsight.db` | SQLite или PostgreSQL URL |
| `STORAGE_PATH` | `./storage` | Каталог зашифрованных документов |

## Приложение

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `APP_PORT` | `8000` | Порт uvicorn |
| `APP_VERSION` | `1.0.0` | Версия в `/health` |
| `CORS_ORIGINS` | localhost | Origins через запятую |
| `SPACY_MODEL` | `ru_core_news_lg` | NLP-модель spaCy |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `LOG_JSON_FORMAT` | `true` | JSON-логи |
| `GRACEFUL_SHUTDOWN_TIMEOUT` | `30` | Drain при остановке (сек) |

## Traefik / HTTPS (prod)

| Переменная | Описание |
|------------|----------|
| `DOMAIN` | Домен для Let's Encrypt |
| `ACME_EMAIL` | Email для ACME |

## Redis и Celery

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `REDIS_URL` | `redis://redis:6379/0` | Брокер Celery |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Backend результатов |

## GPT (ProxyAPI)

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | Ключ ProxyAPI |
| `OPENAI_BASE_URL` | `https://api.proxyapi.ru/openai/v1` |
| `OPENAI_MODEL` | `gpt-4o-mini` |

## Мультитенантность и шифрование

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TENANT_MODE` | `true` | Включить multi-tenant |
| `ENCRYPTION_ENABLED` | `true` | Шифрование файлов |
| `ENCRYPTION_KEY` | — | Ключ age (или через файл) |
| `ENCRYPTION_KEY_PATH` | `secrets/encryption_key.txt` | Путь к ключу |
| `SUPER_ADMIN_EMAIL` | — | Email суперадмина |
| `SUPER_ADMIN_PASSWORD` | — | Пароль (первый запуск) |
| `DEFAULT_TENANT_NAME` | `Default Clinic` | Имя tenant по умолчанию |
| `DEFAULT_TENANT_SUBDOMAIN` | `default` | Subdomain по умолчанию |

## Self-healing RAG

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SELF_HEALING_ENABLED` | `true` | Автовосстановление |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embeddings |
| `SIMILARITY_THRESHOLD` | `0.75` | Порог similarity |
| `MAX_RETRY_ATTEMPTS` | `2` | Retry GPT |

## Webhooks

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `WEBHOOK_ENABLED` | `true` | Исходящие webhooks |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | Таймаут HTTP |
| `WEBHOOK_RETRY_COUNT` | `3` | Повторы |
| `WEBHOOK_PUBLIC_BASE_URL` | — | Базовый URL для callbacks |

## Биллинг

| Переменная | Описание |
|------------|----------|
| `BILLING_ENABLED` | `false` = без лимитов (тест) |
| `STRIPE_*` | Stripe keys и price IDs |
| `YOOKASSA_*` | ЮKassa |
| `FREEMIUM_ANALYSIS_LIMIT` | `5` |
| `PRO_ANALYSIS_LIMIT` | `100` |
| `ENTERPRISE_ANALYSIS_LIMIT` | `999999` |
| `PRO_PRICE_RUB/USD` | Цены в коп/центах |

## Экспорт

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `EXPORT_MAX_ROWS` | `10000` | Лимит строк Excel |
| `EXPORT_MAX_COLUMNS` | `50` | Лимит колонок |
| `EXPORT_TEMP_DIR` | `./storage/exports` | Временные файлы |

## Бэкап

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `BACKUP_ENABLED` | `true` | Автобэкап |
| `BACKUP_DIR` | `/backups` | Каталог архивов |
| `BACKUP_RETENTION_DAYS` | `7` | Дни |
| `BACKUP_RETENTION_WEEKS` | `4` | Недели |
| `BACKUP_RETENTION_MONTHS` | `12` | Месяцы |
| `BACKUP_SCHEDULE_FULL` | `0 2 * * *` | Полный бэкап (cron) |
| `BACKUP_SCHEDULE_DB` | `0 * * * *` | БД каждый час |
| `BACKUP_ENCRYPTION_ENABLED` | `false` | Шифрование архива |
| `BACKUP_ALERT_MAX_AGE_HOURS` | `48` | Алерт если нет бэкапа |

## Telegram

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `TELEGRAM_CHAT_ID` | Chat для алертов |
| `TELEGRAM_BOT_ENABLED` | `false` |
| `TELEGRAM_BOT_WEBHOOK_URL` | URL вебхука |
| `TELEGRAM_LINK_CODE_TTL` | `600` сек |

## UI

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DEFAULT_THEME` | `light` | `light` / `dark` / `system` |

## DICOM

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DICOM_ENABLED` | `true` | Модуль DICOM |
| `DICOM_MAX_FILE_SIZE_MB` | `500` | Лимит загрузки |
| `DICOM_STORAGE_PATH` | `./storage/dicom` | Хранилище |
| `DICOM_THUMBNAIL_SIZE` | `256x256` | Размер превью |

## OpenTelemetry

| Переменная | Описание |
|------------|----------|
| `OTEL_ENABLED` | Трейсинг |
| `OTEL_SERVICE_NAME` | `medinsight` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector URL |

## WebSocket

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `WEBSOCKET_ENABLED` | `true` | Real-time |
| `WEBSOCKET_HEARTBEAT_INTERVAL` | `30` | Heartbeat (сек) |
| `WEBSOCKET_MAX_CONNECTIONS` | `1000` | Лимит соединений |

## Rate limiting

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `RATE_LIMIT_ENABLED` | `true` | Лимиты |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `10` | Логин |
| `RATE_LIMIT_REGISTER_PER_HOUR` | `5` | Регистрация |

## Email

| Переменная | Описание |
|------------|----------|
| `SMTP_HOST`, `SMTP_PORT` | SMTP сервер |
| `SMTP_USER`, `SMTP_PASSWORD` | Auth |
| `SMTP_FROM` | From address |
| `EMAIL_ENABLED` | Включить email |
| `FRONTEND_URL` | Базовый URL фронта |

## Пример .env.production

```bash
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=sqlite:////app/data/medinsight.db
REDIS_URL=redis://redis:6379/0
APP_ENV=production
CORS_ORIGINS=https://medinsight.fileguardian.info
ENCRYPTION_ENABLED=true
OPENAI_API_KEY=sk-...
FRONTEND_URL=https://medinsight.fileguardian.info
```
