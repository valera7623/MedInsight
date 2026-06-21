import asyncio
import logging
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.core.metrics import CONTENT_TYPE_LATEST, render_metrics
from app.core.redis import close_redis_connection
from app.core.shutdown import shutdown_manager
from app.database import Base, bootstrap_system, close_db_connection, engine, run_migrations
from app.middleware.audit import AuditMiddleware
from app.middleware.logging import LoggingMiddleware
from app.middleware.usage_limit import UsageLimitMiddleware
from app.routes import admin, analytics, documents, export, health, patients, payments, predictions, users, webhooks
from app.utils.logging import configure_logging
from app.webhooks import stripe as stripe_webhook
from app.webhooks import yookassa as yookassa_webhook
from app.auth import router as auth_router
from fastapi.staticfiles import StaticFiles

configure_logging()
logger = logging.getLogger(__name__)

# Tracks in-flight requests so shutdown can drain them before closing resources.
_inflight = {"count": 0}
_inflight_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Shutdown handlers
# ---------------------------------------------------------------------------
def _close_chroma() -> None:
    if not settings.SELF_HEALING_ENABLED:
        logger.info("ChromaDB: self-healing disabled, nothing to close")
        return
    try:
        import chromadb

        chromadb.api.client.SharedSystemClient.clear_system_cache()
        logger.info("ChromaDB system cache cleared")
    except Exception as exc:  # noqa: BLE001
        logger.info("ChromaDB: nothing to close (%s)", exc)


def _revoke_celery_tasks() -> None:
    try:
        from app.tasks.celery_app import celery_app, redis_available

        if not redis_available():
            logger.info("Celery: broker unavailable, skipping revoke")
            return
        inspector = celery_app.control.inspect(timeout=2)
        active = inspector.active() or {}
        task_ids = [t["id"] for tasks in active.values() for t in tasks]
        if not task_ids:
            logger.info("Celery: no active tasks to revoke")
            return
        celery_app.control.revoke(task_ids, terminate=True)
        logger.info("Celery: revoked %d active task(s)", len(task_ids))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Celery revoke failed: %s", exc)


async def _drain_requests() -> None:
    """Wait for in-flight requests to finish, up to the configured timeout."""
    deadline = time.monotonic() + settings.GRACEFUL_SHUTDOWN_TIMEOUT
    while _inflight["count"] > 0 and time.monotonic() < deadline:
        logger.info("Draining: %d in-flight request(s)...", _inflight["count"])
        await asyncio.sleep(0.5)
    if _inflight["count"] > 0:
        logger.warning("Drain timeout: %d request(s) still in-flight", _inflight["count"])
    else:
        logger.info("All in-flight requests drained")


def _register_shutdown_handlers(executor: ThreadPoolExecutor) -> None:
    # Order matters: drain traffic first, then tear down dependencies.
    shutdown_manager.register_handler(
        "drain_requests", _drain_requests, timeout=settings.GRACEFUL_SHUTDOWN_TIMEOUT + 5
    )
    shutdown_manager.register_handler("revoke_celery_tasks", _revoke_celery_tasks, timeout=5)
    shutdown_manager.register_handler("close_database", close_db_connection, timeout=5)
    shutdown_manager.register_handler("close_redis", close_redis_connection, timeout=5)
    shutdown_manager.register_handler("close_chromadb", _close_chroma, timeout=5)
    shutdown_manager.register_handler(
        "close_executor", lambda: executor.shutdown(wait=True, cancel_futures=False), timeout=10
    )


def _install_signal_handlers() -> None:
    """Log SIGTERM / SIGINT and delegate to the existing handler.

    Uvicorn installs its own ``signal.signal`` handlers (``handle_exit``) that
    flip ``should_exit`` and begin a graceful stop — which in turn drives the
    lifespan shutdown where our :data:`shutdown_manager` runs. We therefore
    *chain* to that handler instead of replacing it; replacing it would clean up
    resources but leave the server running. When no server handler is present
    (e.g. running standalone), we trigger shutdown ourselves and stop the loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if threading.current_thread() is not threading.main_thread():
        # signal.signal() only works on the main thread.
        return

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            previous = signal.getsignal(sig)
        except (ValueError, OSError):
            continue

        def make_handler(signum: int, prev):
            name = signal.Signals(signum).name

            def handler(received_signum, frame):
                logger.info("Received %s — initiating graceful shutdown", name)
                if callable(prev):
                    # Hand off to uvicorn so the server actually stops; lifespan
                    # shutdown then runs our cleanup exactly once.
                    prev(received_signum, frame)
                elif loop is not None:
                    loop.create_task(_standalone_shutdown(loop))

            return handler

        try:
            signal.signal(sig, make_handler(sig, previous))
        except (ValueError, OSError, RuntimeError):
            logger.debug("Could not install handler for %s", sig)


async def _standalone_shutdown(loop: asyncio.AbstractEventLoop) -> None:
    await shutdown_manager.shutdown()
    loop.stop()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    Path(settings.STORAGE_PATH, "encrypted").mkdir(parents=True, exist_ok=True)
    Path(settings.ENCRYPTION_KEY_PATH).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    run_migrations()
    bootstrap_system()

    if settings.SELF_HEALING_ENABLED:
        try:
            from app.services.self_healing.vector_store import seed_knowledge_base

            imported, skipped = seed_knowledge_base()
            logger.info("Self-healing seed fixes: %d imported, %d skipped", imported, skipped)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Self-healing seed failed: %s", exc)

    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="medinsight")
    app.state.executor = executor
    _register_shutdown_handlers(executor)
    _install_signal_handlers()

    logger.info(
        "MedInsight v%s started. Storage: %s, DB: %s",
        settings.APP_VERSION,
        settings.STORAGE_PATH,
        settings.DATABASE_URL,
    )

    yield

    # --- shutdown (also reached when uvicorn handles the signal) ---
    logger.info("Lifespan shutdown triggered")
    await shutdown_manager.shutdown()


app = FastAPI(
    title="MedInsight",
    description="Clinical analytics platform",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(AuditMiddleware)
app.add_middleware(UsageLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def track_inflight_requests(request: Request, call_next):
    """Count in-flight requests so graceful shutdown can drain them."""
    async with _inflight_lock:
        _inflight["count"] += 1
    try:
        return await call_next(request)
    finally:
        async with _inflight_lock:
            _inflight["count"] -= 1


# Outermost middleware: assigns X-Request-ID, binds log context, logs each request.
app.add_middleware(LoggingMiddleware)


app.include_router(health.router)
app.include_router(auth_router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
# Inbound payment provider webhooks (no /api prefix, no auth — verified by signature)
app.include_router(stripe_webhook.router)
app.include_router(yookassa_webhook.router)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/metrics")
def metrics():
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)


@app.get("/login")
def login_page():
    return FileResponse(static_dir / "login.html")


@app.get("/")
def dashboard_page():
    return FileResponse(static_dir / "index.html")


@app.get("/patients")
def patients_page():
    return FileResponse(static_dir / "patients.html")


@app.get("/patient/{patient_id}")
def patient_detail_page(patient_id: int):
    return FileResponse(static_dir / "patient.html")


@app.get("/admin")
def admin_page():
    return FileResponse(static_dir / "admin.html")
