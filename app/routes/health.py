"""Health / readiness / liveness probes for Docker & Kubernetes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config import settings
from app.core.metrics import health_status
from app.core.redis import ping_redis
from app.database import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


def _check_db() -> tuple[bool, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_redis() -> tuple[bool, str]:
    try:
        return (True, "ok") if ping_redis() else (False, "ping failed")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_celery() -> tuple[bool, str]:
    """Optional: ping any live Celery worker with a 2s timeout."""
    try:
        from app.tasks.celery_app import celery_app

        replies = celery_app.control.ping(timeout=2)
        if replies:
            return True, f"{len(replies)} worker(s)"
        return False, "no workers responded"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_chroma() -> tuple[bool, str]:
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collections = client.list_collections()
        return True, f"{len(collections)} collection(s)"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


@router.get("/health")
def health():
    """Basic health: the process is up and serving."""
    return {"status": "ok", "version": settings.APP_VERSION}


@router.get("/health/live")
def liveness():
    """Liveness probe — only confirms the event loop is responsive."""
    return {"status": "alive"}


@router.get("/health/ready")
def readiness(response: Response):
    """Readiness probe — verifies every critical dependency.

    Returns 200 when all required checks pass, otherwise 503 with details.
    Celery and ChromaDB are treated as optional (degraded, not fatal).
    """
    checks: dict[str, dict] = {}
    all_required_ok = True

    for name, fn, required in (
        ("database", _check_db, True),
        ("redis", _check_redis, True),
        ("celery", _check_celery, False),
        ("chromadb", _check_chroma, False) if settings.SELF_HEALING_ENABLED else (None, None, None),
    ):
        if name is None:
            continue
        ok, detail = fn()
        checks[name] = {"ok": ok, "detail": detail, "required": required}
        health_status.labels(component=name).set(1 if ok else 0)
        if required and not ok:
            all_required_ok = False

    health_status.labels(component="overall").set(1 if all_required_ok else 0)

    if not all_required_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "version": settings.APP_VERSION, "checks": checks}

    return {"status": "ok", "version": settings.APP_VERSION, "checks": checks}
