"""TAR archive creation and export for audit logs."""

from __future__ import annotations

import json
import logging
import tarfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import AuditLog
from app.services.audit_exporter import AuditExporter
from app.services.crypto_audit import CryptoAudit
from app.services.siem_target_manager import SiemTargetManager

logger = logging.getLogger(__name__)


class AuditArchive:
    """Create, sign, and export tamper-evident audit archives."""

    def __init__(self, db: Session | None = None) -> None:
        self._db = db
        self._owns_db = db is None

    def _session(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def close(self) -> None:
        if self._owns_db and self._db is not None:
            self._db.close()
            self._db = None

    def create_archive(self, from_date: datetime, to_date: datetime) -> str:
        db = self._session()
        archive_dir = Path(settings.AUDIT_ARCHIVE_DIR)
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"audit_{from_date.date()}_{to_date.date()}_{stamp}.tar.gz"
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.created_at >= from_date, AuditLog.created_at <= to_date)
            .order_by(AuditLog.id.asc())
            .all()
        )
        jsonl_path = archive_dir / f"audit_{stamp}.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(
                    json.dumps(
                        {
                            "id": row.id,
                            "user_id": row.user_id,
                            "tenant_id": row.tenant_id,
                            "action": row.action,
                            "resource_type": row.resource_type,
                            "resource_id": row.resource_id,
                            "ip_address": row.ip_address,
                            "user_agent": row.user_agent,
                            "details": row.details,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                            "signature": row.signature,
                            "signed_at": row.signed_at.isoformat() if row.signed_at else None,
                        },
                        default=str,
                    )
                    + "\n"
                )
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(jsonl_path, arcname=jsonl_path.name)
        jsonl_path.unlink(missing_ok=True)
        logger.info("Created audit archive %s (%d events)", archive_path, len(rows))
        return str(archive_path)

    def sign_archive(self, archive_path: str) -> str:
        return CryptoAudit.sign_archive(archive_path)

    def verify_archive(self, archive_path: str, signature: str) -> bool:
        return CryptoAudit.verify_archive(archive_path, signature)

    def export_archive(self, archive_path: str, target: dict | None = None) -> bool:
        target = target or SiemTargetManager.get_default_target()
        path = Path(archive_path)
        if not path.exists():
            raise FileNotFoundError(archive_path)
        event = {
            "id": 0,
            "action": "audit.archive.export",
            "resource_type": "audit_archive",
            "details": {"path": str(path), "size_bytes": path.stat().st_size},
            "created_at": datetime.utcnow(),
            "signature": self.sign_archive(archive_path),
        }
        exporter = AuditExporter(self._session())
        try:
            fmt = target.get("format", settings.SIEM_EXPORT_PROTOCOL)
            return exporter.export_batch([event], fmt, target)
        finally:
            exporter.close()
