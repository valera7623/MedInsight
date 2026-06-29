# pg_dump/pg_restore without apt install postgresql-client (slow/unreliable on VPS).
FROM postgres:15-bookworm AS pgclient

# Build Python wheels that need a compiler.
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml poetry.lock ./

ARG INSTALL_SPACY_MODEL=0
ARG SPACY_MODEL_URL=https://github.com/explosion/spacy-models/releases/download/ru_core_news_lg-3.8.0/ru_core_news_lg-3.8.0-py3-none-any.whl

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=5

RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --without dev,test,docs --no-ansi --no-root \
    && poetry install --only nlp --no-ansi --no-root \
    && pip install --no-cache-dir "pydicom>=2.4.0" \
    && python -c "import pydicom, numpy; from PIL import Image; print('DICOM deps OK', pydicom.__version__)" \
    && if [ "$INSTALL_SPACY_MODEL" = "1" ]; then \
         pip install --no-cache-dir --retries 1 --timeout 120 \
           "${SPACY_MODEL_URL}" \
         || echo "WARNING: ru_core_news_lg not installed — NER will use regex fallback"; \
       else \
         echo "Skipping spaCy model download (INSTALL_SPACY_MODEL=0, regex-only NER)"; \
       fi

FROM python:3.12-slim-bookworm

WORKDIR /app

ARG BUILD_DOCS=0

# Runtime OS packages only (no build-essential, no postgresql-client meta-package).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-dejavu-core \
        ca-certificates \
        curl \
        libpq5 \
        antiword \
    && rm -rf /var/lib/apt/lists/*

COPY --from=pgclient /usr/lib/postgresql/15/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=pgclient /usr/lib/postgresql/15/bin/pg_restore /usr/local/bin/pg_restore

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# /help/ — use pre-built site/ from the repo (CI). BUILD_DOCS=1 rebuilds inside the image (dev only).
RUN if [ -f site/index.html ]; then \
      echo "Documentation site/ found ($(du -sh site | cut -f1)) — /help/ enabled"; \
    elif [ "$BUILD_DOCS" = "1" ]; then \
      pip install --no-cache-dir poetry \
      && poetry config virtualenvs.create false \
      && poetry install --only docs --no-ansi --no-root \
      && python scripts/generate_api_docs.py --import-app \
      && mkdocs build; \
    else \
      echo "WARNING: site/ missing and BUILD_DOCS=0 — /help/ disabled"; \
    fi

RUN mkdir -p storage data chroma_data secrets

EXPOSE 8000

RUN chmod +x scripts/start_celery_worker.sh scripts/start_celery_beat.sh 2>/dev/null || true

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
