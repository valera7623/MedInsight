# Configuration

All settings are via environment variables (`.env` or `.env.production`).

## Required

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | JWT and cryptography (≥32 characters) | `openssl rand -hex 32` |
| `DATABASE_URL` | SQLite or PostgreSQL | `sqlite:///./medinsight.db` |
| `REDIS_URL` | Celery broker and cache | `redis://redis:6379/0` |

## Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | `development` / `production` |
| `APP_PORT` | `8000` | uvicorn port |
| `APP_VERSION` | `1.0.0` | Version in `/health` |
| `CORS_ORIGINS` | `*` | Allowed origins (comma-separated) |
| `LOG_LEVEL` | `INFO` | Log level |

## Security and encryption

| Variable | Description |
|----------|-------------|
| `AGE_PUBLIC_KEY` | age public key for file encryption |
| `AGE_SECRET_KEY` | Private key (server only!) |
| `ENCRYPTION_ENABLED` | `true` / `false` |

Key generation:

```bash
age-keygen -o age-key.txt
# AGE_PUBLIC_KEY = age1...
# AGE_SECRET_KEY = AGE-SECRET-KEY-1...
```

## GPT / ProxyAPI

| Variable | Description |
|----------|-------------|
| `PROXYAPI_KEY` | ProxyAPI key (OpenAI-compatible) |
| `PROXYAPI_BASE_URL` | API base URL |
| `GPT_MODEL` | Model, e.g. `gpt-4o-mini` |

Without a key, rule-based fallback is used.

## Email (SMTP)

| Variable | Description |
|----------|-------------|
| `SMTP_HOST`, `SMTP_PORT` | SMTP server |
| `SMTP_USER`, `SMTP_PASSWORD` | Credentials |
| `SMTP_FROM` | Sender address |
| `FRONTEND_URL` | Base URL for links in emails |

## Telegram

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | @BotFather token |
| `TELEGRAM_WEBHOOK_SECRET` | Webhook secret |

## DICOM

| Variable | Default | Description |
|----------|---------|-------------|
| `DICOM_MAX_FILE_SIZE_MB` | `500` | Upload limit |
| `DICOM_STORAGE_PATH` | `storage/dicom` | Storage directory |

## Backup

| Variable | Description |
|----------|-------------|
| `BACKUP_ENABLED` | `true` / `false` |
| `BACKUP_SCHEDULE_CRON` | Schedule (Celery Beat) |
| `BACKUP_RETENTION_DAYS` | Archive retention period |

## Multi-tenancy

| Variable | Description |
|----------|-------------|
| `DEFAULT_TENANT_SUBDOMAIN` | Default subdomain |
| `TENANT_HEADER` | Header for API (optional) |

## Celery

| Variable | Description |
|----------|-------------|
| `CELERY_BROKER_URL` | Usually = `REDIS_URL` |
| `CELERY_RESULT_BACKEND` | Result backend |

## Applying changes

```bash
docker compose -f docker-compose.prod.yml restart app worker beat
```

Full list: [environment-variables.md](../deployment/environment-variables.md).
