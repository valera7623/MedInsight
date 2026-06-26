"""Admin endpoints for cache statistics and maintenance."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.core.cache import cache_service
from app.database import get_db
from app.models import CacheStats, User
from app.services.cache_manager import get_cache_manager
from app.services.static_cache import StaticCache
from app.tasks.cache_tasks import cleanup_static_cache, warmup_cache

router = APIRouter(prefix="/admin/cache", tags=["admin"])
logger = logging.getLogger(__name__)


class CacheInvalidateRequest(BaseModel):
    patient_id: int | None = None
    all: bool = False


class CacheWarmupRequest(BaseModel):
    patient_ids: list[int] = Field(default_factory=list)


@router.get("/stats")
async def cache_stats(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    mgr = get_cache_manager(db)
    stats = await mgr.get_stats()
    rows = (
        db.query(
            CacheStats.cache_type,
            func.count(CacheStats.id),
            func.coalesce(func.sum(CacheStats.size_bytes), 0),
        )
        .group_by(CacheStats.cache_type)
        .all()
    )
    stats["db_entries"] = [
        {"cache_type": r[0], "count": r[1], "size_bytes": r[2]} for r in rows
    ]
    return stats


@router.post("/invalidate")
async def cache_invalidate(
    body: CacheInvalidateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    if body.all:
        removed = StaticCache().invalidate_all()
        cache_service.invalidate_pattern_sync("docx:*")
        return {"status": "ok", "removed_files": removed, "scope": "all"}
    if body.patient_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="patient_id or all=true required")
    mgr = get_cache_manager(db)
    await mgr.invalidate(body.patient_id)
    return {"status": "ok", "patient_id": body.patient_id}


@router.post("/warmup")
def cache_warmup(
    body: CacheWarmupRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    if not body.patient_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="patient_ids required")
    task = warmup_cache.delay(body.patient_ids)
    return {"status": "queued", "job_id": task.id, "patient_ids": body.patient_ids}


@router.post("/cleanup")
def cache_cleanup(
    current_user: Annotated[User, Depends(require_admin)],
):
    task = cleanup_static_cache.delay()
    return {"status": "queued", "job_id": task.id}
