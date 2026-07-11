"""Archive audit logs older than retention period."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditLog

logger = logging.getLogger(__name__)


def archive_expired_audit_logs(db: Session) -> int:
    if not settings.AUDIT_ARCHIVE_ENABLED or settings.AUDIT_RETENTION_DAYS <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=settings.AUDIT_RETENTION_DAYS)
    rows = db.query(AuditLog).filter(AuditLog.created_at < cutoff).limit(5000).all()
    if not rows:
        return 0
    archive_dir = Path(settings.AUDIT_ARCHIVE_DIR)
    archive_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = archive_dir / f"audit_archive_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(
                json.dumps(
                    {
                        "id": row.id,
                        "tenant_id": row.tenant_id,
                        "user_id": row.user_id,
                        "action": row.action,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "details": row.details,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            db.delete(row)
    db.commit()
    logger.info("Archived %d audit rows to %s", len(rows), path)
    return len(rows)
