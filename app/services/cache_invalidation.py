"""Cache invalidation tied to DB cache version records."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import cache_service
from app.models import CacheVersion

logger = logging.getLogger(__name__)


class CacheInvalidationService:
    """Bump version counters and purge Redis keys when data changes."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    @staticmethod
    def _scope_key(scope: str, entity_id: int) -> str:
        return f"{scope}:{entity_id}"

    def bump_version(self, scope_key: str) -> int:
        if self.db is None:
            return 0
        row = self.db.query(CacheVersion).filter(CacheVersion.cache_key == scope_key).first()
        if row is None:
            row = CacheVersion(cache_key=scope_key, version=1)
            self.db.add(row)
        else:
            row.version += 1
            row.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(row)
        return row.version

    def get_cache_version(self, scope_key: str) -> int:
        if self.db is None:
            return 0
        row = self.db.query(CacheVersion).filter(CacheVersion.cache_key == scope_key).first()
        return row.version if row else 0

    def invalidate_for_patient(self, patient_id: int, tenant_id: int | None = None) -> None:
        scope = self._scope_key("patient", patient_id)
        self.bump_version(scope)
        cache_service.invalidate_pattern_sync(f"docx:{patient_id}:*")
        cache_service.invalidate_pattern_sync(f"dicom:studies:patient:{patient_id}*")
        cache_service.invalidate_pattern_sync("patients:*")
        self._invalidate_http_api_cache("patients")
        if settings.STATIC_CACHE_ENABLED:
            from app.services.static_cache import StaticCache

            StaticCache().invalidate(patient_id)
        if tenant_id is not None:
            self.invalidate_for_tenant(tenant_id)
        logger.info("Cache invalidated for patient %s", patient_id)

    def invalidate_for_tenant(self, tenant_id: int) -> None:
        scope = self._scope_key("tenant", tenant_id)
        self.bump_version(scope)
        cache_service.invalidate_pattern_sync(f"patients:tenant:{tenant_id}:*")
        cache_service.invalidate_pattern_sync(f"dashboard:tenant:{tenant_id}:*")
        cache_service.invalidate_pattern_sync(f"dicom:studies:tenant:{tenant_id}:*")
        self._invalidate_http_api_cache("patients", "analytics/dashboard", "dicom/studies")
        logger.info("Cache invalidated for tenant %s", tenant_id)

    @staticmethod
    def _invalidate_http_api_cache(*path_prefixes: str) -> None:
        """Drop middleware GET cache entries for API list endpoints."""
        for prefix in path_prefixes:
            cache_service.invalidate_pattern_sync(f"http_cache:GET:/api/{prefix}*")

    def invalidate_for_user(self, user_id: int) -> None:
        scope = self._scope_key("user", user_id)
        self.bump_version(scope)
        cache_service.invalidate_pattern_sync(f"dashboard:*:user:{user_id}*")
        logger.info("Cache invalidated for user %s", user_id)

    def invalidate_dicom_for_patient(self, patient_id: int) -> None:
        cache_service.invalidate_pattern_sync(f"dicom:studies:patient:{patient_id}*")
        cache_service.invalidate_pattern_sync(f"dicom:frame:*:patient:{patient_id}*")
        self.bump_version(self._scope_key("patient", patient_id))

    def invalidate_docx_template(self) -> None:
        self.bump_version("docx:template")
        cache_service.invalidate_pattern_sync("docx:*")
        logger.info("DOCX template cache invalidated")


def get_cache_version(db: Session, scope_key: str) -> int:
    return CacheInvalidationService(db).get_cache_version(scope_key)


def invalidate_patient_cache(db: Session, patient_id: int, tenant_id: int | None = None) -> None:
    CacheInvalidationService(db).invalidate_for_patient(patient_id, tenant_id)


def invalidate_tenant_cache(db: Session, tenant_id: int) -> None:
    CacheInvalidationService(db).invalidate_for_tenant(tenant_id)


def invalidate_dicom_patient_cache(db: Session, patient_id: int) -> None:
    CacheInvalidationService(db).invalidate_dicom_for_patient(patient_id)
