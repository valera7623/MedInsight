# Backup

## Why

MedInsight stores the database, encrypted documents, and DICOM. Regular backups protect against data loss from disk failure or failed upgrades.

## What is included

| Component | Path |
|-----------|------|
| SQLite DB | `medinsight.db` |
| Documents | `storage/documents/` |
| DICOM | `storage/dicom/` |
| age keys | from `.env` (separately!) |

## Automatic backup (Celery Beat)

With `BACKUP_ENABLED=true`, the `backup_task` runs on schedule `BACKUP_SCHEDULE_CRON`.

Archives are saved in `backups/` with age encryption.

## Manual backup

```bash
cd ~/medinsight
docker compose -f docker-compose.prod.yml exec app \
  python -c "from app.tasks.backup_task import run_backup; run_backup()"
```

Or via script (if available):

```bash
./scripts/backup.sh
```

## Restore

1. Stop services:

```bash
docker compose -f docker-compose.prod.yml down
```

2. Decrypt and unpack the archive:

```bash
age -d -i age-key.txt backups/medinsight-YYYYMMDD.tar.gz.age | tar xzf -
```

3. Restore `.env` and age keys.
4. Start:

```bash
./deploy.sh production
```

## Key storage

!!! danger "Critical"
    Without **AGE_SECRET_KEY**, encrypted files are **unrecoverable**. Store keys separately from backups (secret manager, offline copy).

## Rotation

Old archives are removed automatically via `BACKUP_RETENTION_DAYS` (default 30 days).

## Recommendations

- Copy `backups/` to external storage (S3, another server).
- Test restore quarterly.
- Do not use `docker system prune --volumes` on production — see `scripts/docker_cleanup.sh`.
