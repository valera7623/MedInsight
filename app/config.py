from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    SECRET_KEY: str = "change-me-in-production-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "sqlite:///./medinsight.db"
    STORAGE_PATH: str = "./storage"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8000"
    SPACY_MODEL: str = "ru_core_news_lg"

    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/1"

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.proxyapi.ru/openai/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"

    TENANT_MODE: bool = True
    ENCRYPTION_ENABLED: bool = True
    ENCRYPTION_KEY: str = ""
    ENCRYPTION_KEY_PATH: str = "secrets/encryption_key.txt"

    SUPER_ADMIN_EMAIL: str = "admin@medinsight.com"
    SUPER_ADMIN_PASSWORD: str = "change_me_super_admin"
    DEFAULT_TENANT_NAME: str = "Default Clinic"
    DEFAULT_TENANT_SUBDOMAIN: str = "default"

    # Phase 4: Self-Healing RAG
    SELF_HEALING_ENABLED: bool = True
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    SIMILARITY_THRESHOLD: float = 0.75
    MAX_RETRY_ATTEMPTS: int = 2

    # Phase 4: Webhooks
    WEBHOOK_ENABLED: bool = True
    WEBHOOK_TIMEOUT_SECONDS: float = 10.0
    WEBHOOK_RETRY_COUNT: int = 3
    WEBHOOK_RETRY_DELAY_SECONDS: float = 2.0
    WEBHOOK_FAILURE_DEACTIVATE_THRESHOLD: int = 5
    WEBHOOK_PUBLIC_BASE_URL: str = ""

    # Phase 4: Payments — Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_ID_PRO: str = ""
    STRIPE_PRICE_ID_ENTERPRISE: str = ""
    STRIPE_SUCCESS_URL: str = "http://localhost:8000/payment/success"
    STRIPE_CANCEL_URL: str = "http://localhost:8000/payment/cancel"

    # Phase 4: Payments — ЮKassa
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    YOOKASSA_RETURN_URL_SUCCESS: str = "http://localhost:8000/payment/success"
    YOOKASSA_RETURN_URL_CANCEL: str = "http://localhost:8000/payment/cancel"

    # Phase 4: Plan limits
    FREEMIUM_ANALYSIS_LIMIT: int = 5
    PRO_ANALYSIS_LIMIT: int = 100
    ENTERPRISE_ANALYSIS_LIMIT: int = 999999
    PRO_PRICE_RUB: int = 199000  # kopecks (1990 ₽)
    PRO_PRICE_USD: int = 1999  # cents ($19.99)
    ENTERPRISE_PRICE_RUB: int = 999000  # kopecks (9990 ₽)
    ENTERPRISE_PRICE_USD: int = 9999  # cents ($99.99)

    # Billing master switch. When false: no analysis limits, checkout disabled
    # (testing / maintenance mode). Mirrors ReportAgent's BILLING_ENABLED.
    BILLING_ENABLED: bool = True

    # Phase 7: Excel export
    EXPORT_MAX_ROWS: int = 10000  # rows above this go through Celery (async)
    EXPORT_MAX_COLUMNS: int = 50
    EXPORT_TEMP_DIR: str = "./storage/exports"

    # Phase 8: Backup & Restore
    BACKUP_ENABLED: bool = True
    BACKUP_DIR: str = "./backups"
    BACKUP_RETENTION_DAYS: int = 7
    BACKUP_RETENTION_WEEKS: int = 4
    BACKUP_RETENTION_MONTHS: int = 12
    BACKUP_SCHEDULE_FULL: str = "0 2 * * *"   # daily at 02:00
    BACKUP_SCHEDULE_DB: str = "0 * * * *"     # hourly
    BACKUP_SCHEDULE_CLEANUP: str = "0 3 * * *"  # daily at 03:00
    BACKUP_MAX_SIZE_MB: int = 10240  # abort backup if exceeded (10 GB)
    BACKUP_ENCRYPTION_ENABLED: bool = False
    BACKUP_ENCRYPTION_KEY: str = ""
    BACKUP_ALERT_MAX_AGE_HOURS: int = 48
    # Optional Telegram alerting for backup health
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Phase 5: Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    RATE_LIMIT_RESET_PER_HOUR: int = 3

    # Phase 5: Graceful Shutdown
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 30

    # Phase 5: App version (exposed via /health)
    APP_VERSION: str = "1.0.0"

    # Phase 6: Email (SMTP)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@medinsight.com"
    SMTP_USE_TLS: bool = True  # STARTTLS on port 587; set False for port 465 + SMTP_USE_SSL
    SMTP_USE_SSL: bool = False
    SMTP_TIMEOUT: float = 10.0
    EMAIL_ENABLED: bool = True
    EMAIL_VERIFICATION_ENABLED: bool = True
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    EMAIL_PASSWORD_RESET_EXPIRE_HOURS: int = 2
    EMAIL_PREDICTION_READY_ENABLED: bool = True
    EMAIL_LIMIT_EXCEEDED_ENABLED: bool = True
    FRONTEND_URL: str = "https://medinsight.fileguardian.info"

    # Phase 6: Structured logging
    LOG_LEVEL: str = "INFO"
    LOG_JSON_FORMAT: bool = True
    LOG_INCLUDE_REQUEST_ID: bool = True
    LOG_INCLUDE_USER_ID: bool = True
    LOG_SLOW_QUERY_MS: float = 500.0  # log SQL slower than this (0 disables)


settings = Settings()
