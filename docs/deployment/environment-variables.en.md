# Environment Variables

Full reference from `.env.example`.

## Security and JWT

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | JWT secret (≥32 characters). **Required** |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_DAYS` | `7` | Token lifetime |

## Database and storage

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./medinsight.db` | SQLite or PostgreSQL URL |
| `STORAGE_PATH` | `./storage` | Encrypted documents directory |

## Application

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_PORT` | `8000` | uvicorn port |
| `APP_VERSION` | `1.0.0` | Version in `/health` |
| `CORS_ORIGINS` | localhost | Origins comma-separated |
| `SPACY_MODEL` | `ru_core_news_lg` | spaCy NLP model |
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_JSON_FORMAT` | `true` | JSON logs |
| `GRACEFUL_SHUTDOWN_TIMEOUT` | `30` | Drain on shutdown (sec) |

## Traefik / HTTPS (prod)

| Variable | Description |
|----------|-------------|
| `DOMAIN` | Domain for Let's Encrypt |
| `ACME_EMAIL` | Email for ACME |

## Redis and Celery

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/1` | Result backend |

## GPT (ProxyAPI)

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | ProxyAPI key |
| `OPENAI_BASE_URL` | `https://api.proxyapi.ru/openai/v1` |
| `OPENAI_MODEL` | `gpt-4o-mini` |

## Multi-tenancy and encryption

| Variable | Default | Description |
|----------|---------|-------------|
| `TENANT_MODE` | `true` | Enable multi-tenant |
| `ENCRYPTION_ENABLED` | `true` | File encryption |
| `ENCRYPTION_KEY` | — | age key (or via file) |
| `ENCRYPTION_KEY_PATH` | `secrets/encryption_key.txt` | Key file path |
| `SUPER_ADMIN_EMAIL` | — | Superadmin email |
| `SUPER_ADMIN_PASSWORD` | — | Password (first run) |
| `DEFAULT_TENANT_NAME` | `Default Clinic` | Default tenant name |
| `DEFAULT_TENANT_SUBDOMAIN` | `default` | Default subdomain |

## Self-healing RAG

| Variable | Default | Description |
|----------|---------|-------------|
| `SELF_HEALING_ENABLED` | `true` | Auto-recovery |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | ChromaDB |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embeddings |
| `SIMILARITY_THRESHOLD` | `0.75` | Similarity threshold |
| `MAX_RETRY_ATTEMPTS` | `2` | GPT retry |

## Webhooks

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_ENABLED` | `true` | Outbound webhooks |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | HTTP timeout |
| `WEBHOOK_RETRY_COUNT` | `3` | Retries |
| `WEBHOOK_PUBLIC_BASE_URL` | — | Base URL for callbacks |

## Billing

| Variable | Description |
|----------|-------------|
| `BILLING_ENABLED` | `false` = no limits (test) |
| `STRIPE_*` | Stripe keys and price IDs |
| `YOOKASSA_*` | YooKassa |
| `FREEMIUM_ANALYSIS_LIMIT` | `5` |
| `PRO_ANALYSIS_LIMIT` | `100` |
| `ENTERPRISE_ANALYSIS_LIMIT` | `999999` |
| `PRO_PRICE_RUB/USD` | Prices in kopecks/cents |

## Export

| Variable | Default | Description |
|----------|---------|-------------|
| `EXPORT_MAX_ROWS` | `10000` | Excel row limit |
| `EXPORT_MAX_COLUMNS` | `50` | Column limit |
| `EXPORT_TEMP_DIR` | `./storage/exports` | Temp files |

## Backup

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_ENABLED` | `true` | Auto backup |
| `BACKUP_DIR` | `/backups` | Archive directory |
| `BACKUP_RETENTION_DAYS` | `7` | Days |
| `BACKUP_RETENTION_WEEKS` | `4` | Weeks |
| `BACKUP_RETENTION_MONTHS` | `12` | Months |
| `BACKUP_SCHEDULE_FULL` | `0 2 * * *` | Full backup (cron) |
| `BACKUP_SCHEDULE_DB` | `0 * * * *` | DB hourly |
| `BACKUP_ENCRYPTION_ENABLED` | `false` | Archive encryption |
| `BACKUP_ALERT_MAX_AGE_HOURS` | `48` | Alert if no backup |

## Telegram

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token |
| `TELEGRAM_CHAT_ID` | Chat for alerts |
| `TELEGRAM_BOT_ENABLED` | `false` |
| `TELEGRAM_BOT_WEBHOOK_URL` | Webhook URL |
| `TELEGRAM_LINK_CODE_TTL` | `600` sec |

## UI

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_THEME` | `light` | `light` / `dark` / `system` |

## DICOM

| Variable | Default | Description |
|----------|---------|-------------|
| `DICOM_ENABLED` | `true` | DICOM module |
| `DICOM_MAX_FILE_SIZE_MB` | `500` | Upload limit |
| `DICOM_STORAGE_PATH` | `./storage/dicom` | Storage |
| `DICOM_THUMBNAIL_SIZE` | `256x256` | Thumbnail size |

## OpenTelemetry

| Variable | Description |
|----------|-------------|
| `OTEL_ENABLED` | Tracing |
| `OTEL_SERVICE_NAME` | `medinsight` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Collector URL |

## WebSocket

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBSOCKET_ENABLED` | `true` | Real-time |
| `WEBSOCKET_HEARTBEAT_INTERVAL` | `30` | Heartbeat (sec) |
| `WEBSOCKET_MAX_CONNECTIONS` | `1000` | Connection limit |

## Rate limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Limits |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `10` | Login |
| `RATE_LIMIT_REGISTER_PER_HOUR` | `5` | Registration |

## Email

| Variable | Description |
|----------|-------------|
| `SMTP_HOST`, `SMTP_PORT` | SMTP server |
| `SMTP_USER`, `SMTP_PASSWORD` | Auth |
| `SMTP_FROM` | From address |
| `EMAIL_ENABLED` | Enable email |
| `FRONTEND_URL` | Frontend base URL |

## Example .env.production

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
