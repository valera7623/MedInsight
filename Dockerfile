FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-dejavu-core \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-nlp.txt ./

# spaCy model ~500MB with GitHub — часто падает на VPS (SSL EOF).
# По умолчанию ПРОПУСКАЕМ: приложение работает в regex-only режиме.
# Для установки модели: docker compose build --build-arg INSTALL_SPACY_MODEL=1
ARG INSTALL_SPACY_MODEL=0
ARG SPACY_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/ru_core_news_lg-3.8.0/ru_core_news_lg-3.8.0-py3-none-any.whl

# VPS builds often hit slow PyPI; default pip timeout (15s) is too short for large wheels.
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=5

RUN pip install --no-cache-dir --retries 5 --timeout 300 -r requirements.txt \
    && pip install --no-cache-dir --retries 5 --timeout 300 -r requirements-nlp.txt \
    && if [ "$INSTALL_SPACY_MODEL" = "1" ]; then \
         pip install --no-cache-dir --retries 1 --timeout 120 \
           "${SPACY_MODEL_URL}" \
         || echo "WARNING: ru_core_news_lg not installed — NER will use regex fallback"; \
       else \
         echo "Skipping spaCy model download (INSTALL_SPACY_MODEL=0, regex-only NER)"; \
       fi

COPY . .

RUN pip install --no-cache-dir --retries 3 --timeout 120 -r requirements-docs.txt \
    && python scripts/generate_api_docs.py --import-app \
    && mkdocs build

RUN mkdir -p storage data chroma_data secrets

EXPOSE 8000

RUN chmod +x scripts/start_celery_worker.sh scripts/start_celery_beat.sh 2>/dev/null || true

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
