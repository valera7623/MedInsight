# Мониторинг

## Health-эндпоинты

| URL | Назначение |
|-----|------------|
| `GET /health` | Базовая проверка (200 OK) |
| `GET /health/ready` | БД + Redis (для load balancer) |
| `GET /health/live` | Процесс жив |

```bash
curl -s http://localhost:8000/health/ready | jq
```

Ожидаемый ответ:

```json
{
  "status": "ready",
  "database": "ok",
  "redis": "ok"
}
```

## Docker

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f app --tail=100
docker compose -f docker-compose.prod.yml logs -f worker --tail=100
```

## Celery

```bash
docker compose -f docker-compose.prod.yml exec worker \
  celery -A app.celery_app inspect active
```

## Метрики Prometheus

Эндпоинт `GET /metrics` (если включён `PROMETHEUS_ENABLED=true`).

## Журнал аудита

Админ-панель → **Аудит**: входы, загрузки, удаления, смена ролей.

API: `GET /api/admin/audit` (только admin).

## Алерты (рекомендации)

| Событие | Действие |
|---------|----------|
| `/health/ready` ≠ 200 | Перезапуск контейнеров, проверка Redis/БД |
| Worker не обрабатывает задачи | `restart worker`, проверить Redis |
| Диск > 85% | `scripts/docker_cleanup.sh weekly` |
| Ошибки GPT | Проверить `PROXYAPI_KEY`, fallback активен |

## Логи приложения

Уровень: `LOG_LEVEL=INFO` (prod) или `DEBUG` (dev).

Структурированные логи в stdout → собирает Docker.

## Uptime

Внешний мониторинг (UptimeRobot, Pingdom) на:

- `https://your-domain/health/ready`
- `https://your-domain/` (опционально)

## Self-healing

Автоматическое восстановление Celery/Redis — см. [Self-healing](../developer-guide/self-healing.md).

## Очистка Docker

```bash
./scripts/docker_cleanup.sh deploy   # после каждого деплоя
./scripts/docker_cleanup.sh weekly   # cron по воскресеньям
```

Не используйте `docker system prune --volumes` — удалит данные volumes.
