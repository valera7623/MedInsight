# Retention policy

| Data class | Default retention | Mechanism |
|------------|-------------------|-----------|
| Clinical records | Until tenant deletion / DSAR erasure | Admin + DSAR API |
| Audit logs | 365 days (configurable) | `AUDIT_RETENTION_DAYS`, archive job |
| Backups | GFS: 7d / 4w / 12m | Celery + `BACKUP_*` settings |
| Cache (Redis/static) | 5 min – 7 days | TTL |
| RAG / Chroma | Until tenant/patient delete | Manual purge in erasure checklist |
| Sessions | 7 days | Redis TTL |

Legal hold: set `legal_hold=true` in tenant settings to skip automated purge (future automation).
