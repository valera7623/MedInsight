"""Unified DOCX cache: Redis (hot, 1h) + static disk (persistent)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from io import BytesIO
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import cache_enabled, cache_service, docx_cache_key
from app.services.cache_invalidation import get_cache_version
from app.services.docx_generator import DocxGenerator, save_docx_to_patient_reports
from app.services.static_cache import StaticCache

logger = logging.getLogger(__name__)


class CacheManager:
    """Two-tier DOCX cache with hit/miss counters."""

    redis_hits: int = 0
    disk_hits: int = 0
    misses: int = 0

    def __init__(self, db: Session | None = None, static_cache: StaticCache | None = None) -> None:
        self.db = db
        self.static_cache = static_cache or StaticCache()

    def _redis_ttl(self) -> int:
        return settings.REDIS_CACHE_DOCX_HOT_TTL

    def _versioned_redis_key(self, patient_id: int, options: dict[str, Any]) -> str:
        version = get_cache_version(self.db, f"patient:{patient_id}") if self.db else 0
        return docx_cache_key(patient_id, options, version)

    def _record_stats(self, cache_type: str, key: str, size_bytes: int, *, created: bool = False) -> None:
        if self.db is None:
            return
        from app.models import CacheStats

        row = (
            self.db.query(CacheStats)
            .filter(CacheStats.cache_type == cache_type, CacheStats.key == key)
            .first()
        )
        now = datetime.utcnow()
        if row is None:
            row = CacheStats(
                cache_type=cache_type,
                key=key,
                size_bytes=size_bytes,
                created_at=now,
                last_accessed_at=now,
                access_count=1,
            )
            self.db.add(row)
        else:
            row.size_bytes = size_bytes
            row.last_accessed_at = now
            row.access_count = (row.access_count or 0) + 1
        self.db.commit()

    def get_docx_sync(self, patient_id: int, options: dict[str, Any]) -> tuple[bytes | None, str | None]:
        """Return (docx_bytes, source) where source is redis|disk|None."""
        redis_key = self._versioned_redis_key(patient_id, options)
        if cache_enabled():
            cached = cache_service.get_bytes_sync(redis_key)
            if cached:
                CacheManager.redis_hits += 1
                self._record_stats("redis", redis_key, len(cached))
                logger.info("DOCX cache HIT redis patient=%s", patient_id)
                return cached, "redis"

        static_key = self.static_cache.get_cache_key(patient_id, options)
        if settings.STATIC_CACHE_ENABLED and self.static_cache.has_cached(static_key):
            data = self.static_cache.load(static_key)
            if data:
                CacheManager.disk_hits += 1
                self._record_stats("static", static_key, len(data))
                if cache_enabled():
                    cache_service.set_bytes_sync(redis_key, data, self._redis_ttl())
                logger.info("DOCX cache HIT disk patient=%s", patient_id)
                return data, "disk"

        CacheManager.misses += 1
        return None, None

    def set_docx_sync(
        self,
        patient_id: int,
        options: dict[str, Any],
        data: bytes,
        *,
        also_save_report: bool = True,
    ) -> str | None:
        """Store in Redis + static cache; optionally persist under storage/reports."""
        report_path: str | None = None
        if also_save_report and self.db is not None:
            buffer = BytesIO(data)
            report_path = save_docx_to_patient_reports(patient_id, buffer, suffix="patient_card")

        redis_key = self._versioned_redis_key(patient_id, options)
        if cache_enabled():
            cache_service.set_bytes_sync(redis_key, data, self._redis_ttl())
            self._record_stats("redis", redis_key, len(data), created=True)

        if settings.STATIC_CACHE_ENABLED:
            static_key = self.static_cache.get_cache_key(patient_id, options)
            self.static_cache.save(static_key, data)
            self._record_stats("static", static_key, len(data), created=True)

        return report_path

    async def get_docx(self, patient_id: int, options: dict[str, Any]) -> bytes | None:
        data, _ = await asyncio.to_thread(self.get_docx_sync, patient_id, options)
        return data

    async def set_docx(self, patient_id: int, options: dict[str, Any], data: bytes) -> None:
        await asyncio.to_thread(self.set_docx_sync, patient_id, options, data, also_save_report=False)

    async def invalidate(self, patient_id: int) -> None:
        await asyncio.to_thread(self._invalidate_sync, patient_id)

    def _invalidate_sync(self, patient_id: int) -> None:
        if self.db is not None:
            from app.services.cache_invalidation import invalidate_patient_cache

            invalidate_patient_cache(self.db, patient_id)
        if settings.STATIC_CACHE_ENABLED:
            self.static_cache.invalidate(patient_id)

    async def get_stats(self) -> dict[str, Any]:
        static_stats = self.static_cache.get_cache_stats()
        return {
            "redis_hits": CacheManager.redis_hits,
            "disk_hits": CacheManager.disk_hits,
            "misses": CacheManager.misses,
            "static_cache": static_stats,
            "redis_enabled": cache_enabled(),
            "static_enabled": settings.STATIC_CACHE_ENABLED,
        }

    async def warmup(self, patient_ids: list[int], options: dict[str, Any] | None = None) -> int:
        if self.db is None:
            return 0
        opts = options or {"sections": None, "watermark": settings.DOCX_WATERMARK}
        if opts.get("sections") is None:
            from app.services.docx_templates import DEFAULT_PATIENT_CARD_SECTIONS

            opts = {**opts, "sections": list(DEFAULT_PATIENT_CARD_SECTIONS)}

        warmed = 0
        generator = DocxGenerator(self.db)
        for patient_id in patient_ids:
            existing, _ = self.get_docx_sync(patient_id, opts)
            if existing:
                continue
            try:
                buffer = generator.generate_patient_card(patient_id, opts)
                self.set_docx_sync(patient_id, opts, buffer.getvalue())
                warmed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Warmup failed for patient %s: %s", patient_id, exc)
        return warmed


def get_cache_manager(db: Session | None = None) -> CacheManager:
    return CacheManager(db=db)
