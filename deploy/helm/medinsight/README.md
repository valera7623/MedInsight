# MedInsight Helm chart (starter)

Minimal Kubernetes starter — not production HA. Adjust `values.yaml` before use.

## Install

```bash
helm install medinsight ./deploy/helm/medinsight \
  --set image.repository=your-registry/medinsight-app \
  --set image.tag=latest \
  --set env.SECRET_KEY=change-me \
  --set postgres.password=change-me
```

## Components

| Template | Description |
|----------|-------------|
| `deployment-app.yaml` | FastAPI app |
| `deployment-celery.yaml` | Celery worker (optional) |
| `redis.yaml` | Redis broker |
| `postgres.yaml` | PostgreSQL (emptyDir — use external DB in prod) |
| `service-app.yaml` | ClusterIP for app |

## Notes

- Set `ALEMBIC_ENABLED=true` in `values.env` and run migrations via init job or deploy pipeline before traffic.
- For production, disable bundled Postgres/Redis and point `DATABASE_URL` / `REDIS_URL` to managed services.
- Celery replicas: `celery.replicas` in values.
