# Деплой (администратор)

Руководство для DevOps и системных администраторов.

## Варианты деплоя

| Способ | Когда использовать |
|--------|-------------------|
| **GitHub Actions** | Продакшен (рекомендуется) |
| **deploy.sh** | Ручной деплой на VPS |
| **Docker Compose** | Локально / staging |

## Быстрый прод-деплой (GitHub Actions)

1. Настройте Secrets в репозитории `valera7623/MedInsight`:
   - `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`
   - `SECRET_KEY`, `APP_PORT`, `CORS_ORIGINS`
2. Push в ветку `main` запускает `.github/workflows/deploy.yml`.
3. Pipeline: **test** → **deploy** (SSH на VPS).

```bash
gh run list --workflow=deploy.yml --limit 1
gh run watch --exit-status
```

## Ручной деплой на VPS

```bash
ssh medinsight-vps
cd ~/medinsight
git fetch origin && git reset --hard origin/main
./deploy.sh production
```

Скрипт `deploy.sh`:

- копирует `.env` из `.env.production` (если есть);
- собирает образы `docker compose -f docker-compose.prod.yml build`;
- поднимает сервисы `up -d`;
- применяет SQL-миграции из `app/db/migrations/`;
- вызывает `scripts/docker_cleanup.sh deploy`.

## Проверка после деплоя

```bash
curl -s http://localhost:8000/health/ready
# {"status":"ready","database":"ok","redis":"ok"}
```

## Структура на VPS

```
~/medinsight/
├── .env                 # секреты (не в git)
├── docker-compose.prod.yml
├── storage/             # зашифрованные файлы + DICOM
├── backups/             # age-архивы
└── deploy.sh
```

## Порты

| Сервис | Порт (по умолчанию) |
|--------|---------------------|
| FastAPI (app) | 8000 |
| Redis | 6379 (внутри Docker) |

Nginx/Caddy на VPS проксирует HTTPS → `localhost:8000`.

## Подробнее

- [Docker](../deployment/docker.md)
- [VPS](../deployment/vps.md)
- [CI/CD](../deployment/ci-cd.md)
- [Переменные окружения](../deployment/environment-variables.md)
