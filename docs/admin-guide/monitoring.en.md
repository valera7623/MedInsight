# Monitoring

## Health endpoints

| URL | Purpose |
|-----|---------|
| `GET /health` | Basic check (200 OK) |
| `GET /health/ready` | DB + Redis (for load balancer) |
| `GET /health/live` | Process is alive |

```bash
curl -s http://localhost:8000/health/ready | jq
```

Expected response:

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

## Prometheus metrics

Endpoint `GET /metrics` (if `PROMETHEUS_ENABLED=true`).

## Audit log

Admin panel → **Audit**: logins, uploads, deletions, role changes.

API: `GET /api/admin/audit` (admin only).

## Alerts (recommendations)

| Event | Action |
|-------|--------|
| `/health/ready` ≠ 200 | Restart containers, check Redis/DB |
| Worker not processing tasks | `restart worker`, check Redis |
| Disk > 85% | `scripts/docker_cleanup.sh weekly` |
| GPT errors | Check `PROXYAPI_KEY`, fallback is active |

## Application logs

Level: `LOG_LEVEL=INFO` (prod) or `DEBUG` (dev).

Structured logs to stdout → collected by Docker.

## Uptime

External monitoring (UptimeRobot, Pingdom) on:

- `https://your-domain/health/ready`
- `https://your-domain/` (optional)

## Self-healing

Automatic Celery/Redis recovery — see [Self-healing](../developer-guide/self-healing.md).

## Docker cleanup

```bash
./scripts/docker_cleanup.sh deploy   # after each deploy
./scripts/docker_cleanup.sh weekly   # cron on Sundays
```

Do not use `docker system prune --volumes` — it removes volume data.
