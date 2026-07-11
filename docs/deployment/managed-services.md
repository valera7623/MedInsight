# Managed services migration

Hybrid path from single VPS to cloud-managed components.

## PostgreSQL

Set `MANAGED_DATABASE_URL` and point `DATABASE_URL` / `PRODUCTION_DATABASE_URL` to the managed instance.
Enable streaming replica and PITR in the cloud console.

## Redis

Set `MANAGED_REDIS_URL` and update `REDIS_URL`, `CELERY_RESULT_BACKEND`.
Disable public Redis ports; use VPC/private network.

## Object storage

Enable `OBJECT_STORAGE_ENABLED=true` with `OBJECT_STORAGE_BUCKET` and endpoint for documents/DICOM.
Migrate `./storage` via `aws s3 sync` or compatible tool.

## Secrets

Prefer `VAULT_ENABLED=true` with HashiCorp Vault or cloud secret manager instead of flat `.env` on VPS.

## Kubernetes

See [Helm chart](../../deploy/helm/medinsight/README.md) for HPA, Ingress, and Alembic init job templates.
