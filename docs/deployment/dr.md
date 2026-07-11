# Disaster recovery runbook

## Targets

| Metric | Default |
|--------|---------|
| RTO | 4 hours |
| RPO | 1 hour |

## Failover steps

1. Confirm outage via `/health/ready` and Prometheus alerts.
2. Restore PostgreSQL from latest `pg_dump` (hourly) or managed PITR.
3. Restore file storage from full backup or S3 sync.
4. Rotate `SECRET_KEY` and encryption keys if compromise suspected.
5. Redeploy `./deploy.sh production` on standby host or K8s cluster.
6. Verify smoke tests and notify tenants.

## Cross-region backup

Enable `BACKUP_S3_ENABLED=true` and replicate bucket to secondary region.
Document bucket name and restore credentials in ops vault.

## Contacts

Platform on-call and security lead — update for production.
