# CI/CD — GitHub Actions

## Workflow

Файл: `.github/workflows/deploy.yml`

```mermaid
flowchart LR
    Push[Push to main] --> Test[job: test]
    Test -->|success| Deploy[job: deploy]
    Deploy --> SSH[SSH to VPS]
    SSH --> Reset[git reset --hard]
    Reset --> DeploySh[./deploy.sh production]
    DeploySh --> Health[health/ready]
```

## Job: test

- Checkout
- Setup Python
- `pip install -r requirements.txt`
- Запуск тестов (`pytest` или `scripts/test_*.py`)

## Job: deploy

Условие: `main` branch, test passed.

Шаги:

1. SSH на VPS (`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`)
2. `cd ~/medinsight && git fetch && git reset --hard origin/main`
3. `./deploy.sh production`
4. Smoke: `curl localhost:8000/health/ready`

## Secrets (GitHub)

| Secret | Описание |
|--------|----------|
| `VPS_HOST` | IP или hostname VPS |
| `VPS_USER` | SSH user (напр. `smdg`) |
| `VPS_SSH_KEY` | Приватный ключ deploy |
| `SECRET_KEY` | JWT secret (inject в .env) |
| `APP_PORT` | Порт приложения |
| `CORS_ORIGINS` | Allowed origins |

## Мониторинг pipeline

```bash
gh run list --workflow=deploy.yml --limit 5
gh run watch --exit-status
gh run view RUN_ID --log-failed
```

## Локальная проверка перед push

```bash
python -m pytest
python scripts/test_dicom.py
python scripts/test_health.py
```

## Откат

```bash
ssh medinsight-vps
cd ~/medinsight
git log --oneline -5
git reset --hard COMMIT_SHA
./deploy.sh production
```

## Branch policy

Деплой **только из `main`**. Feature branches — через PR + review.

## Pre-commit (опционально)

Если настроен pre-commit hook — проверяет lint/format перед коммитом.
