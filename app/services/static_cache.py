"""On-disk static cache for generated DOCX files."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.cache import hash_options

logger = logging.getLogger(__name__)


class StaticCache:
    """Persistent filesystem cache complementing Redis hot cache."""

    def __init__(self, cache_dir: str | None = None) -> None:
        base = cache_dir or settings.STATIC_CACHE_DIR
        self.cache_dir = Path(base)
        self.docx_dir = self.cache_dir / "docx"
        if settings.STATIC_CACHE_ENABLED:
            self.docx_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_cache_key(patient_id: int, options: dict[str, Any]) -> str:
        return f"{patient_id}_{hash_options(options)}"

    def get_file_path(self, key: str) -> Path:
        patient_id = key.split("_", 1)[0]
        return self.docx_dir / patient_id / f"{key}.docx"

    def _meta_path(self, key: str) -> Path:
        return self.get_file_path(key).with_suffix(".docx.meta.json")

    def has_cached(self, key: str) -> bool:
        if not settings.STATIC_CACHE_ENABLED:
            return False
        path = self.get_file_path(key)
        return path.is_file() and path.stat().st_size > 0

    def get_file_info(self, key: str) -> dict[str, Any]:
        path = self.get_file_path(key)
        if not path.is_file():
            return {}
        stat = path.stat()
        data_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        meta: dict[str, Any] = {
            "key": key,
            "path": str(path),
            "size_bytes": stat.st_size,
            "created_at": datetime.utcfromtimestamp(stat.st_ctime).isoformat(),
            "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            "sha256": data_hash,
        }
        meta_path = self._meta_path(key)
        if meta_path.is_file():
            try:
                meta.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        return meta

    def save(self, key: str, data: bytes) -> Path:
        if not settings.STATIC_CACHE_ENABLED:
            raise RuntimeError("Static cache is disabled")
        path = self.get_file_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        meta = {
            "key": key,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "saved_at": datetime.utcnow().isoformat(),
        }
        self._meta_path(key).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        logger.debug("Static cache saved: %s (%d bytes)", path, len(data))
        return path

    def load(self, key: str) -> bytes | None:
        if not self.has_cached(key):
            return None
        try:
            return self.get_file_path(key).read_bytes()
        except OSError as exc:
            logger.warning("Static cache read failed for %s: %s", key, exc)
            return None

    def invalidate(self, patient_id: int) -> int:
        if not settings.STATIC_CACHE_ENABLED:
            return 0
        patient_dir = self.docx_dir / str(patient_id)
        if not patient_dir.is_dir():
            return 0
        count = sum(1 for _ in patient_dir.glob("*"))
        shutil.rmtree(patient_dir, ignore_errors=True)
        logger.info("Static cache invalidated patient=%s files=%d", patient_id, count)
        return count

    def invalidate_all(self) -> int:
        if not settings.STATIC_CACHE_ENABLED or not self.docx_dir.is_dir():
            return 0
        count = sum(1 for _ in self.docx_dir.rglob("*") if _.is_file())
        shutil.rmtree(self.docx_dir, ignore_errors=True)
        self.docx_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Static cache cleared: %d files", count)
        return count

    def get_cache_size(self) -> int:
        if not self.docx_dir.is_dir():
            return 0
        return sum(f.stat().st_size for f in self.docx_dir.rglob("*.docx") if f.is_file())

    def get_cache_stats(self) -> dict[str, Any]:
        files: list[dict[str, Any]] = []
        if self.docx_dir.is_dir():
            for path in self.docx_dir.rglob("*.docx"):
                if not path.is_file():
                    continue
                stat = path.stat()
                files.append(
                    {
                        "path": str(path),
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                    }
                )
        files.sort(key=lambda x: x["size_bytes"], reverse=True)
        total_size = sum(item["size_bytes"] for item in files)
        return {
            "file_count": len(files),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "top_files": files[:10],
            "cache_dir": str(self.cache_dir),
        }

    def _meta_path_for_file(self, docx_path: Path) -> Path:
        return docx_path.parent / f"{docx_path.name}.meta.json"

    def cleanup_old(self, days: int | None = None) -> int:
        if not settings.STATIC_CACHE_ENABLED or not self.docx_dir.is_dir():
            return 0
        cutoff = datetime.utcnow() - timedelta(days=days or settings.STATIC_CACHE_RETENTION_DAYS)
        removed = 0
        for path in list(self.docx_dir.rglob("*.docx")):
            if "meta.json" in path.name:
                continue
            if datetime.utcfromtimestamp(path.stat().st_mtime) < cutoff:
                meta_path = self._meta_path_for_file(path)
                path.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
                removed += 1
        logger.info("Static cache cleanup_old removed %d files (>%s days)", removed, days)
        return removed

    def cleanup_by_size(self, max_size_mb: int | None = None) -> int:
        if not settings.STATIC_CACHE_ENABLED or not self.docx_dir.is_dir():
            return 0
        limit = (max_size_mb or settings.STATIC_CACHE_MAX_SIZE_MB) * 1024 * 1024
        files = sorted(
            (p for p in self.docx_dir.rglob("*.docx") if p.is_file() and "meta.json" not in p.name),
            key=lambda p: p.stat().st_mtime,
        )
        total = sum(p.stat().st_size for p in files)
        removed = 0
        while total > limit and files:
            victim = files.pop(0)
            size = victim.stat().st_size
            self._meta_path_for_file(victim).unlink(missing_ok=True)
            victim.unlink(missing_ok=True)
            total -= size
            removed += 1
        logger.info("Static cache cleanup_by_size removed %d files (limit %s MB)", removed, max_size_mb)
        return removed
