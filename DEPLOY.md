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

## 4. Как работает деплой

При каждом `push` в `main`:

1. CI: smoke-test (`from app.main import app`)
2. SSH на VPS
3. `git clone` / `git pull` в `~/medinsight`
4. `docker compose up -d --build` (порт **8000**)

## 5. Проверка после деплоя

```bash
curl http://186.246.3.65:8000/health
```

UI:
- http://186.246.3.65:8000/login
- http://186.246.3.65:8000/

Логи на VPS:

```bash
ssh medinsight-vps
cd ~/medinsight
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f app
```

## 6. Ручной деплой (без GitHub)

```bash
ssh medinsight-vps
cd ~/medinsight && git pull && ./deploy.sh production
```

## 7. HTTPS через nginx (опционально)

На VPS уже работает nginx на 80/443. Пример конфига: `scripts/nginx-medinsight.conf.example`

После настройки поддомена обновите `CORS_ORIGINS` в GitHub Secrets.
