"""Backup & restore for the database (SQLite or PostgreSQL) and the ``storage/`` tree.

Layout under ``BACKUP_DIR``::

    backups/
      full/      backup_<ts>.tar.gz          (db + storage + sanitized config + metadata)
      db/        backup_<ts>.db.gz           (SQLite) or backup_<ts>.sql.gz (PostgreSQL)
      storage/   backup_<ts>.storage.tar.gz  (storage tree)
      metadata/  backup_<ts>.json            (version, sizes, sha256 checksums)

Design notes:
* SQLite: ``sqlite3.Connection.backup`` (consistent, no app downtime).
* PostgreSQL: ``pg_dump`` custom format, restore via ``pg_restore``.
* ``.env`` is sanitised (secrets stripped) before being placed in a full backup.
* Optional age passphrase encryption (pyrage) when BACKUP_ENCRYPTION_ENABLED.
* Every method is defensive and records a ``BackupLog`` row + Prometheus metrics.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.metrics import (
    backup_age_days,
    backup_duration_seconds,
    backup_size_bytes,
    backup_status_total,
)
from app.database import is_postgresql, sqlite_db_path

logger = logging.getLogger(__name__)

TS_FMT = "%Y-%m-%d_%H-%M-%S"
_SECRET_HINTS = ("KEY", "PASSWORD", "SECRET", "TOKEN")


def _now() -> datetime:
    from app.models._time import utc_now
    return utc_now()


def _upload_backup_to_s3(local_path: Path, backup_id: str, backup_type: str) -> str | None:
    """Upload backup file to S3 when BACKUP_S3_ENABLED. Returns s3 URI or None."""
    if not settings.BACKUP_S3_ENABLED or not settings.BACKUP_S3_BUCKET:
        return None
    try:
        import boto3
    except ImportError:
        logger.warning("boto3 not installed — skipping S3 backup upload")
        return None

    key_prefix = settings.BACKUP_S3_PREFIX.strip("/")
    key = f"{key_prefix}/{backup_type}/{local_path.name}" if key_prefix else f"{backup_type}/{local_path.name}"
    client_kwargs: dict[str, Any] = {}
    if settings.BACKUP_S3_REGION:
        client_kwargs["region_name"] = settings.BACKUP_S3_REGION
    if settings.BACKUP_S3_ENDPOINT_URL:
        client_kwargs["endpoint_url"] = settings.BACKUP_S3_ENDPOINT_URL
    if settings.BACKUP_S3_ACCESS_KEY and settings.BACKUP_S3_SECRET_KEY:
        client_kwargs["aws_access_key_id"] = settings.BACKUP_S3_ACCESS_KEY
        client_kwargs["aws_secret_access_key"] = settings.BACKUP_S3_SECRET_KEY

    try:
        s3 = boto3.client("s3", **client_kwargs)
        s3.upload_file(str(local_path), settings.BACKUP_S3_BUCKET, key)
        uri = f"s3://{settings.BACKUP_S3_BUCKET}/{key}"
        logger.info("Backup %s uploaded to %s", backup_id, uri)
        return uri
    except Exception as exc:  # noqa: BLE001
        logger.exception("S3 upload failed for %s: %s", backup_id, exc)
        send_alert(f"S3 backup upload failed for {backup_id}: {exc}")
        return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _sha256_dir(path: Path) -> str:
    h = hashlib.sha256()
    if path.exists():
        for file in sorted(p for p in path.rglob("*") if p.is_file()):
            h.update(str(file.relative_to(path)).encode())
            with open(file, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
    return "sha256:" + h.hexdigest()


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


class BackupService:
    def __init__(self, backup_dir: str | None = None) -> None:
        self.base = Path(backup_dir or settings.BACKUP_DIR)
        self.storage_path = Path(settings.STORAGE_PATH)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for sub in ("full", "db", "storage", "metadata"):
            (self.base / sub).mkdir(parents=True, exist_ok=True)

    def _db_path(self) -> Path | None:
        return sqlite_db_path(settings.DATABASE_URL)

    # -- helpers ------------------------------------------------------------

    def _sqlite_snapshot(self, dest: Path) -> None:
        """Consistent online copy of the SQLite DB via the backup API."""
        db_path = self._db_path()
        if db_path is None or not db_path.exists():
            raise FileNotFoundError(f"SQLite database not found: {db_path}")
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

    def _pg_dump_snapshot(self, dest: Path) -> None:
        """PostgreSQL logical backup via pg_dump (custom format)."""
        pg_dump = shutil.which("pg_dump")
        if not pg_dump:
            raise RuntimeError(
                "pg_dump not found in PATH — rebuild the app image (Dockerfile copies it from postgres:15-bookworm)"
            )
        url = settings.DATABASE_URL
        cmd = [pg_dump, "--format=custom", "--no-owner", "--dbname", url, "--file", str(dest)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")

    def _db_snapshot(self, dest: Path) -> None:
        if is_postgresql():
            self._pg_dump_snapshot(dest)
        else:
            self._sqlite_snapshot(dest)

    def _sanitized_env(self) -> str:
        """Return .env contents with secret values blanked out."""
        env_path = Path(".env")
        if not env_path.exists():
            return ""
        lines_out: list[str] = []
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                lines_out.append(line)
                continue
            key = line.split("=", 1)[0]
            if any(hint in key.upper() for hint in _SECRET_HINTS):
                lines_out.append(f"{key}=__REDACTED__")
            else:
                lines_out.append(line)
        return "\n".join(lines_out) + "\n"

    def _maybe_encrypt(self, path: Path) -> Path:
        if not settings.BACKUP_ENCRYPTION_ENABLED:
            return path
        key = (settings.BACKUP_ENCRYPTION_KEY or "").strip()
        if not key:
            logger.warning("BACKUP_ENCRYPTION_ENABLED but no key — leaving backup unencrypted")
            return path
        try:
            import pyrage

            data = path.read_bytes()
            encrypted = pyrage.passphrase.encrypt(data, key)
            enc_path = path.with_suffix(path.suffix + ".age")
            enc_path.write_bytes(encrypted)
            path.unlink(missing_ok=True)
            return enc_path
        except Exception as exc:  # noqa: BLE001
            logger.error("Backup encryption failed (%s) — keeping plaintext", exc)
            return path

    def _maybe_decrypt(self, path: Path) -> Path:
        if path.suffix != ".age":
            return path
        key = (settings.BACKUP_ENCRYPTION_KEY or "").strip()
        if not key:
            raise ValueError("Encrypted backup requires BACKUP_ENCRYPTION_KEY")
        import pyrage

        data = pyrage.passphrase.decrypt(path.read_bytes(), key)
        out = path.with_suffix("")  # drop .age
        tmp = Path(tempfile.mkdtemp()) / out.name
        tmp.write_bytes(data)
        return tmp

    def _record(self, **kwargs: Any) -> None:
        """Persist a BackupLog row (best-effort)."""
        try:
            from app.database import SessionLocal
            from app.models import BackupLog

            db = SessionLocal()
            try:
                existing = db.query(BackupLog).filter(BackupLog.backup_id == kwargs["backup_id"]).first()
                if existing:
                    for k, v in kwargs.items():
                        setattr(existing, k, v)
                else:
                    db.add(BackupLog(**kwargs))
                db.commit()
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to record BackupLog: %s", exc)

    def _check_size(self, size_bytes: int, backup_id: str) -> None:
        max_bytes = settings.BACKUP_MAX_SIZE_MB * 1024 * 1024
        if max_bytes and size_bytes > max_bytes:
            msg = f"Backup {backup_id} exceeds max size: {size_bytes / 1e6:.1f}MB > {settings.BACKUP_MAX_SIZE_MB}MB"
            logger.warning(msg)
            send_alert(msg)

    # -- public API ---------------------------------------------------------

    def backup_database(self, backup_id: str | None = None) -> str:
        ts = _now()
        backup_id = backup_id or f"backup_{ts.strftime(TS_FMT)}"
        start = time.monotonic()
        ext = ".sql.gz" if is_postgresql() else ".db.gz"
        dest = self.base / "db" / f"{backup_id}{ext}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                snap = Path(tmp) / ("snapshot.dump" if is_postgresql() else "snapshot.db")
                self._db_snapshot(snap)
                with open(snap, "rb") as fin, gzip.open(dest, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
            final = self._maybe_encrypt(dest)
            size = final.stat().st_size
            duration = time.monotonic() - start
            self._check_size(size, backup_id)
            backup_size_bytes.labels(type="db").set(size)
            backup_duration_seconds.labels(type="db").observe(duration)
            backup_status_total.labels(type="db", result="success").inc()
            backup_age_days.set(0)
            self._record(
                backup_id=backup_id, type="db", status="completed", path=str(final),
                size_bytes=size, duration_seconds=duration, contains_db=True,
                contains_storage=False, contains_config=False, created_at=ts, completed_at=_now(),
            )
            logger.info("DB backup created: %s (%.1f KB)", final, size / 1024)
            _upload_backup_to_s3(final, backup_id, "db")
            return str(final)
        except Exception as exc:  # noqa: BLE001
            backup_status_total.labels(type="db", result="failure").inc()
            self._record(backup_id=backup_id, type="db", status="failed", error_message=str(exc), created_at=ts)
            logger.exception("DB backup failed: %s", exc)
            send_alert(f"DB backup failed: {exc}")
            raise

    def backup_storage(self, backup_id: str | None = None) -> str:
        ts = _now()
        backup_id = backup_id or f"backup_{ts.strftime(TS_FMT)}"
        start = time.monotonic()
        dest = self.base / "storage" / f"{backup_id}.storage.tar.gz"
        try:
            with tarfile.open(dest, "w:gz") as tar:
                if self.storage_path.exists():
                    tar.add(self.storage_path, arcname="storage", filter=_skip_backups_filter)
            final = self._maybe_encrypt(dest)
            size = final.stat().st_size
            duration = time.monotonic() - start
            self._check_size(size, backup_id)
            backup_size_bytes.labels(type="storage").set(size)
            backup_duration_seconds.labels(type="storage").observe(duration)
            backup_status_total.labels(type="storage", result="success").inc()
            self._record(
                backup_id=backup_id, type="storage", status="completed", path=str(final),
                size_bytes=size, duration_seconds=duration, contains_db=False,
                contains_storage=True, contains_config=False, created_at=ts, completed_at=_now(),
            )
            logger.info("Storage backup created: %s (%.1f MB)", final, size / 1e6)
            _upload_backup_to_s3(final, backup_id, "storage")
            return str(final)
        except Exception as exc:  # noqa: BLE001
            backup_status_total.labels(type="storage", result="failure").inc()
            self._record(backup_id=backup_id, type="storage", status="failed", error_message=str(exc), created_at=ts)
            logger.exception("Storage backup failed: %s", exc)
            send_alert(f"Storage backup failed: {exc}")
            raise

    def backup_full(self, backup_id: str | None = None) -> dict:
        ts = _now()
        backup_id = backup_id or f"backup_{ts.strftime(TS_FMT)}"
        start = time.monotonic()
        dest = self.base / "full" / f"{backup_id}.tar.gz"
        meta_path = self.base / "metadata" / f"{backup_id}.json"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                staging = Path(tmp) / "backup"
                (staging / "config").mkdir(parents=True, exist_ok=True)

                # 1) DB snapshot
                db_name = "medinsight.dump" if is_postgresql() else "medinsight.db"
                db_dest = staging / db_name
                self._db_snapshot(db_dest)

                # 2) storage tree
                if self.storage_path.exists():
                    shutil.copytree(
                        self.storage_path, staging / "storage",
                        ignore=shutil.ignore_patterns("exports"),
                    )

                # 3) sanitized config (.env without secrets) + traefik
                env_text = self._sanitized_env()
                if env_text:
                    (staging / "config" / ".env").write_text(env_text, encoding="utf-8")
                if Path("traefik").exists():
                    shutil.copytree("traefik", staging / "config" / "traefik")

                db_size = db_dest.stat().st_size
                storage_size = _dir_size(staging / "storage")
                metadata = {
                    "version": settings.APP_VERSION,
                    "backup_id": backup_id,
                    "type": "full",
                    "created_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "db_size_mb": round(db_size / 1e6, 2),
                    "storage_size_mb": round(storage_size / 1e6, 2),
                    "checksums": {
                        db_name: _sha256_file(db_dest),
                        "storage/": _sha256_dir(staging / "storage"),
                    },
                }
                (staging / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

                with tarfile.open(dest, "w:gz") as tar:
                    tar.add(staging, arcname="backup")

            final = self._maybe_encrypt(dest)
            size = final.stat().st_size
            duration = time.monotonic() - start
            self._check_size(size, backup_id)
            if duration > 300:
                send_alert(f"Backup {backup_id} took {duration:.0f}s (> 5 min)")
            backup_size_bytes.labels(type="full").set(size)
            backup_duration_seconds.labels(type="full").observe(duration)
            backup_status_total.labels(type="full", result="success").inc()
            backup_age_days.set(0)
            self._record(
                backup_id=backup_id, type="full", status="completed", path=str(final),
                size_bytes=size, duration_seconds=duration, contains_db=True,
                contains_storage=True, contains_config=bool(env_text), created_at=ts, completed_at=_now(),
            )
            logger.info("Full backup created: %s (%.1f MB, %.1fs)", final, size / 1e6, duration)
            s3_uri = _upload_backup_to_s3(final, backup_id, "full")
            result = {"backup_id": backup_id, "db_path": str(final), "storage_path": str(final),
                    "path": str(final), "size": size, "duration": round(duration, 2),
                    "metadata": str(meta_path)}
            if s3_uri:
                result["s3_uri"] = s3_uri
            return result
        except Exception as exc:  # noqa: BLE001
            backup_status_total.labels(type="full", result="failure").inc()
            self._record(backup_id=backup_id, type="full", status="failed", error_message=str(exc), created_at=ts)
            logger.exception("Full backup failed: %s", exc)
            send_alert(f"Full backup failed: {exc}")
            raise

    def list_backups(self) -> list[dict]:
        backups: list[dict] = []
        patterns = {
            "full": ("full", "*.tar.gz"),
            "db": ("db", "*.db.gz"),
            "storage": ("storage", "*.storage.tar.gz"),
        }
        for btype, (sub, glob) in patterns.items():
            folder = self.base / sub
            if not folder.exists():
                continue
            for path in folder.glob(glob):
                # backup_id = filename up to the first known suffix
                name = path.name
                for suffix in (".storage.tar.gz", ".db.gz", ".tar.gz", ".age"):
                    if name.endswith(suffix):
                        name = name[: -len(suffix)]
                stat = path.stat()
                contains = {"full": ["db", "storage", "config"], "db": ["db"], "storage": ["storage"]}[btype]
                backups.append({
                    "id": name,
                    "type": btype,
                    "created_at": datetime.utcfromtimestamp(stat.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "size_mb": round(stat.st_size / 1e6, 2),
                    "size_bytes": stat.st_size,
                    "path": str(path),
                    "contains": contains,
                    "encrypted": path.suffix == ".age",
                })
        backups.sort(key=lambda b: b["created_at"], reverse=True)
        return backups

    def _find_backup_path(self, backup_id: str, btype: str | None = None) -> Path | None:
        for b in self.list_backups():
            if b["id"] == backup_id and (btype is None or b["type"] == btype):
                return Path(b["path"])
        return None

    def restore_from_backup(self, backup_path: str, type: str) -> bool:
        """Restore DB and/or storage from a backup file.

        A safety copy of the current DB is taken first (``*.pre-restore``).
        """
        from app.database import close_db_connection

        path = Path(backup_path)
        if not path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        path = self._maybe_decrypt(path)
        start = time.monotonic()

        db_path = self._db_path()
        if db_path is not None and db_path.exists():
            shutil.copy2(db_path, db_path.with_suffix(db_path.suffix + ".pre-restore"))

        # Release DB connections before overwriting the file.
        close_db_connection()

        if type == "db":
            self._restore_db_gz(path, db_path)
        elif type == "storage":
            self._restore_storage_tar(path)
        elif type == "full":
            self._restore_full(path, db_path)
        else:
            raise ValueError(f"Unknown restore type: {type}")

        duration = time.monotonic() - start
        if duration > 300:
            send_alert(f"Restore took {duration:.0f}s (> 5 min)")
        logger.info("Restore (%s) completed in %.1fs", type, duration)
        return True

    def _restore_db_gz(self, gz_path: Path, db_path: Path | None) -> None:
        if is_postgresql():
            with tempfile.TemporaryDirectory() as tmp:
                dump_path = Path(tmp) / "restore.dump"
                with gzip.open(gz_path, "rb") as fin, open(dump_path, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                cmd = [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--dbname",
                    settings.DATABASE_URL,
                    str(dump_path),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    raise RuntimeError(f"pg_restore failed: {result.stderr.strip()}")
            return
        if db_path is None:
            raise ValueError("DB restore requires a SQLite DATABASE_URL")
        with gzip.open(gz_path, "rb") as fin, open(db_path, "wb") as fout:
            shutil.copyfileobj(fin, fout)

    def _restore_storage_tar(self, tar_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(tar_path, "r:gz") as tar:
                _safe_extractall(tar, tmp)
            extracted = Path(tmp) / "storage"
            if extracted.exists():
                self._replace_storage(extracted)

    def _restore_full(self, tar_path: Path, db_path: Path | None) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(tar_path, "r:gz") as tar:
                _safe_extractall(tar, tmp)
            root = Path(tmp) / "backup"
            self._verify_checksums(root)
            db_file = root / "medinsight.db"
            db_dump = root / "medinsight.dump"
            if db_dump.exists() and is_postgresql():
                cmd = [
                    "pg_restore",
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--dbname",
                    settings.DATABASE_URL,
                    str(db_dump),
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    raise RuntimeError(f"pg_restore failed: {result.stderr.strip()}")
            elif db_file.exists() and db_path is not None:
                shutil.copy2(db_file, db_path)
            storage_dir = root / "storage"
            if storage_dir.exists():
                self._replace_storage(storage_dir)

    def _replace_storage(self, new_storage: Path) -> None:
        # Preserve exports dir (transient) and swap the rest.
        if self.storage_path.exists():
            backup_old = self.storage_path.with_name(self.storage_path.name + ".pre-restore")
            if backup_old.exists():
                shutil.rmtree(backup_old, ignore_errors=True)
            shutil.move(str(self.storage_path), str(backup_old))
        shutil.copytree(new_storage, self.storage_path)
        (self.storage_path / "exports").mkdir(parents=True, exist_ok=True)

    def _verify_checksums(self, root: Path) -> None:
        meta = root / "metadata.json"
        if not meta.exists():
            return
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            checks = data.get("checksums", {})
            db_file = root / "medinsight.db"
            if "medinsight.db" in checks and db_file.exists():
                actual = _sha256_file(db_file)
                if actual != checks["medinsight.db"]:
                    raise ValueError("DB checksum mismatch — backup may be corrupted")
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Checksum verification skipped: %s", exc)

    def cleanup_old_backups(self, days_to_keep: int | None = None) -> int:
        """GFS-style rotation: keep N daily + M weekly + K monthly per type."""
        daily = days_to_keep if days_to_keep is not None else settings.BACKUP_RETENTION_DAYS
        weekly = settings.BACKUP_RETENTION_WEEKS
        monthly = settings.BACKUP_RETENTION_MONTHS

        removed = 0
        for btype in ("full", "db", "storage"):
            entries = [b for b in self.list_backups() if b["type"] == btype]
            keep: set[str] = set()
            seen_days: set[str] = set()
            seen_weeks: set[str] = set()
            seen_months: set[str] = set()
            for b in entries:  # newest first
                dt = datetime.strptime(b["created_at"], "%Y-%m-%dT%H:%M:%SZ")
                day = dt.strftime("%Y-%m-%d")
                week = dt.strftime("%Y-%W")
                month = dt.strftime("%Y-%m")
                if len(seen_days) < daily and day not in seen_days:
                    seen_days.add(day); keep.add(b["path"]); continue
                if len(seen_weeks) < weekly and week not in seen_weeks:
                    seen_weeks.add(week); keep.add(b["path"]); continue
                if len(seen_months) < monthly and month not in seen_months:
                    seen_months.add(month); keep.add(b["path"]); continue
            for b in entries:
                if b["path"] not in keep:
                    try:
                        Path(b["path"]).unlink(missing_ok=True)
                        meta = self.base / "metadata" / f"{b['id']}.json"
                        meta.unlink(missing_ok=True)
                        removed += 1
                    except OSError as exc:
                        logger.warning("Failed to remove old backup %s: %s", b["path"], exc)
        logger.info("Backup cleanup removed %d old backups", removed)
        return removed

    def latest_backup_age_hours(self) -> float | None:
        backups = self.list_backups()
        if not backups:
            return None
        newest = datetime.strptime(backups[0]["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        return (datetime.utcnow() - newest).total_seconds() / 3600


def _skip_backups_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
    # Avoid recursively archiving the exports dir (transient files).
    if "/exports/" in tarinfo.name or tarinfo.name.endswith("/exports"):
        return None
    return tarinfo


def _safe_extractall(tar: tarfile.TarFile, dest: str) -> None:
    """Extract guarding against path traversal (Tar slip)."""
    dest_path = Path(dest).resolve()
    for member in tar.getmembers():
        target = (dest_path / member.name).resolve()
        if not str(target).startswith(str(dest_path)):
            raise ValueError(f"Unsafe path in archive: {member.name}")
    tar.extractall(dest)  # noqa: S202 — members validated above


def send_alert(message: str) -> None:
    """Best-effort alert to logs and (optionally) Telegram."""
    logger.warning("[backup-alert] %s", message)
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    chat_id = (settings.TELEGRAM_CHAT_ID or "").strip()
    if not token or not chat_id:
        return
    try:
        import httpx

        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": f"🛟 MedInsight backup: {message}"},
            timeout=5.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Telegram alert failed: %s", exc)


_service: BackupService | None = None


def get_backup_service() -> BackupService:
    global _service
    if _service is None:
        _service = BackupService()
    return _service
