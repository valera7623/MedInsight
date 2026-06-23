# Автодеплой: GitHub Actions → VPS

Цепочка: **localhost (git push)** → **GitHub `valera7623/Medinsight`** → **GitHub Actions** → **VPS `186.246.3.65`**

## 1. Первый push в GitHub

```bash
cd ~/medinsight
git init
git add .
git commit -m "Initial MedInsight MVP"
git branch -M main
git remote add origin https://github.com/valera7623/Medinsight.git
git push -u origin main
```

## 2. SSH-ключ для GitHub Actions

На VPS уже должен быть публичный ключ из `~/.ssh/medinsight_deploy.pub`.

Приватный ключ добавьте в GitHub Secrets:

```bash
cat ~/.ssh/medinsight_deploy
```

Скопируйте **весь** вывод (включая `-----BEGIN/END-----`).

## 3. Secrets в GitHub

Откройте: **https://github.com/valera7623/Medinsight/settings/secrets/actions**

| Secret | Значение | Обязательно |
|--------|----------|-------------|
| `VPS_HOST` | `186.246.3.65` | да |
| `VPS_USER` | `smdg` | да |
| `VPS_SSH_KEY` | содержимое `~/.ssh/medinsight_deploy` | да |
| `APP_SECRET_KEY` | случайная строка (`openssl rand -hex 32`) | да |
| `APP_PORT` | `8000` | нет |
| `CORS_ORIGINS` | `http://186.246.3.65:8000` | нет |
| `POSTGRES_PASSWORD` | надёжный пароль PostgreSQL | да (production) |

## 4. Как работает деплой

При каждом `push` в `main`:

1. CI: smoke-test (`from app.main import app`)
2. SSH на VPS
3. `git clone` / `git pull` в `~/medinsight`
4. `./deploy.sh production` — поднимает **PostgreSQL 15** + app + celery на порту **8000**

## 5. PostgreSQL в production

`./deploy.sh production` автоматически:

1. Запускает контейнер `postgres:15-alpine` (volume `medinsight-postgres`)
2. Устанавливает `DATABASE_URL=postgresql://medinsight:…@postgres:5432/medinsight`
3. Выполняет `create_all` + миграцию `019_migrate_to_postgresql` (JSONB, FTS, UUID, audit-триггеры)
4. Запускает `bootstrap_system` (tenant + super admin)

### Миграция данных SQLite → PostgreSQL

Если на VPS осталась старая SQLite-база в volume `medinsight-data`:

```bash
ssh medinsight-vps
cd ~/medinsight

# Убедитесь, что PostgreSQL уже запущен и схема создана
./deploy.sh production

# Перенос данных (сохраняет integer id)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec app \
  python scripts/migrate_to_postgres.py \
  --sqlite-url sqlite:////app/data/medinsight.db \
  --postgres-url "$PRODUCTION_DATABASE_URL"
```

Проверка:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec app \
  python scripts/test_postgres.py
```

### Бэкап PostgreSQL

Автоматический бэкап (Celery beat) использует `pg_dump` вместо копирования файла `.db`.

Ручной бэкап:

```bash
docker compose exec app python -c "from app.services.backup import BackupService; print(BackupService().backup_database())"
```

Восстановление: `pg_restore` через API `/api/admin/backup/restore` или `scripts/restore.sh`.

## 6. Проверка после деплоя

```bash
curl http://186.246.3.65:8000/health/ready
```

UI:
- http://186.246.3.65:8000/login
- http://186.246.3.65:8000/

Логи на VPS:

```bash
ssh medinsight-vps
cd ~/medinsight
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f app postgres
```

## 7. Ручной деплой (без GitHub)

```bash
ssh medinsight-vps
cd ~/medinsight && git pull && ./deploy.sh production
```

Перед первым production-деплоем задайте в `.env` на VPS:

```env
POSTGRES_PASSWORD=<надёжный-пароль>
PRODUCTION_DATABASE_URL=postgresql://medinsight:<пароль>@postgres:5432/medinsight
DATABASE_URL=postgresql://medinsight:<пароль>@postgres:5432/medinsight
```

## 8. DNS на VPS (Docker / git)

Симптомы:

```
lookup registry-1.docker.io on 127.0.0.53:53: server misbehaving
Could not resolve host: github.com
```

`dig @127.0.0.53` может работать, а Docker/git — нет: демон Docker читает `/etc/resolv.conf`, а не `daemon.json.dns`.

**Исправление (один раз, sudo):**

```bash
cd ~/medinsight
sudo bash scripts/fix-vps-dns.sh
```

Скрипт отключает stub `127.0.0.53`, настраивает `8.8.8.8` / `1.1.1.1` + DNS провайдера, перезапускает `systemd-resolved` и Docker.

Проверка:

```bash
docker pull hello-world
./deploy.sh production
```

## 9. HTTPS через nginx (опционально)

На VPS уже работает nginx на 80/443. Пример конфига: `scripts/nginx-medinsight.conf.example`

После настройки поддомена обновите `CORS_ORIGINS` в GitHub Secrets.

## 9. Локальная разработка (SQLite)

Для быстрого старта без PostgreSQL:

```bash
./deploy.sh          # dev-режим: SQLite в volume /app/data
# или локально:
DATABASE_URL=sqlite:///./medinsight.db uvicorn app.main:app --reload
```

SQLite остаётся для разработки и CI smoke-тестов; production использует только PostgreSQL.
