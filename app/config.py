from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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


settings = Settings()
