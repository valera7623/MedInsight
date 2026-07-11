# Deployment (Administrator)

Guide for DevOps and system administrators.

## Deployment options

| Method | When to use |
|--------|-------------|
| **GitHub Actions** | Production (recommended) |
| **deploy.sh** | Manual deploy on VPS |
| **Docker Compose** | Local / staging |

## Quick production deploy (GitHub Actions)

1. Configure Secrets in the `valera7623/MedInsight` repository:
   - `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`
   - `SECRET_KEY`, `APP_PORT`, `CORS_ORIGINS`
2. Push to `main` triggers `.github/workflows/deploy.yml`.
3. Pipeline: **test** → **deploy** (SSH to VPS).

```bash
gh run list --workflow=deploy.yml --limit 1
gh run watch --exit-status
```

## Manual deploy on VPS

```bash
ssh medinsight-vps
cd ~/medinsight
git fetch origin && git reset --hard origin/main
./deploy.sh production
```

The `deploy.sh` script:

- pulls latest code;
- in production builds `DATABASE_URL` from `POSTGRES_PASSWORD`;
- runs `compose down` + `build` + `up -d` (containers recreated with current `.env`);
- applies SQL migrations from `app/db/migrations/`;
- runs `scripts/docker_cleanup.sh deploy`.

Sync new keys from `.env.example` without overwriting secrets:

```bash
python scripts/sync_env_from_example.py
```

## Post-deploy check

```bash
curl -s http://localhost:8000/health/ready
# {"status":"ready","database":"ok","redis":"ok"}
```

## VPS layout

```
~/medinsight/
├── .env                 # secrets (not in git)
├── docker-compose.prod.yml
├── storage/             # encrypted files + DICOM
├── backups/             # age archives
└── deploy.sh
```

## Ports

| Service | Port (default) |
|---------|----------------|
| FastAPI (app) | 8000 |
| Redis | 6379 (inside Docker) |

Nginx/Caddy on the VPS proxies HTTPS → `localhost:8000`.

## More detail

- [Docker](../deployment/docker.md)
- [VPS](../deployment/vps.md)
- [CI/CD](../deployment/ci-cd.md)
- [Environment variables](../deployment/environment-variables.md)
