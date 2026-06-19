FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-dejavu-core \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-nlp.txt ./

# ru_core_news_lg — wheel с github.com/releases (не raw.githubusercontent.com).
# При сбое сети сборка продолжается: приложение работает в regex-only режиме.
ARG SPACY_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/ru_core_news_lg-3.8.0/ru_core_news_lg-3.8.0-py3-none-any.whl

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-nlp.txt \
    && (for i in 1 2 3; do \
          pip install --no-cache-dir --default-timeout=300 "${SPACY_MODEL_URL}" && exit 0; \
          echo "spaCy model download attempt $i failed, retrying..."; sleep 10; \
        done; \
        echo "WARNING: ru_core_news_lg not installed — NER will use regex fallback"; \
        exit 0)

COPY . .

RUN mkdir -p storage data

EXPOSE 8000

RUN chmod +x scripts/start_celery_worker.sh scripts/start_celery_beat.sh 2>/dev/null || true

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
