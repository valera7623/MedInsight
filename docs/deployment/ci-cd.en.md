# CI/CD — GitHub Actions

## Workflow

File: `.github/workflows/deploy.yml`

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
- Run tests (`pytest` or `scripts/test_*.py`)

## Job: deploy

Condition: `main` branch, test passed.

Steps:

1. SSH to VPS (`VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`)
2. `cd ~/medinsight && git fetch && git reset --hard origin/main`
3. `./deploy.sh production`
4. Smoke: `curl localhost:8000/health/ready`

## Secrets (GitHub)

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | VPS IP or hostname |
| `VPS_USER` | SSH user (e.g. `smdg`) |
| `VPS_SSH_KEY` | Deploy private key |
| `SECRET_KEY` | JWT secret (inject into .env) |
| `APP_PORT` | Application port |
| `CORS_ORIGINS` | Allowed origins |

## Pipeline monitoring

```bash
gh run list --workflow=deploy.yml --limit 5
gh run watch --exit-status
gh run view RUN_ID --log-failed
```

## Local check before push

```bash
python -m pytest
python scripts/test_dicom.py
python scripts/test_health.py
```

## Rollback

```bash
ssh medinsight-vps
cd ~/medinsight
git log --oneline -5
git reset --hard COMMIT_SHA
./deploy.sh production
```

## Branch policy

Deploy **only from `main`**. Feature branches — via PR + review.

## Pre-commit (optional)

If pre-commit hook is configured — runs lint/format before commit.
