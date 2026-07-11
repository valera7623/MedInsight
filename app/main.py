import asyncio
import logging
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.core.metrics import CONTENT_TYPE_LATEST, render_metrics
from app.core.redis import close_redis_connection
from app.core.cache import close_async_cache, close_sync_binary_cache
from app.core.shutdown import shutdown_manager
from app.database import Base, bootstrap_system, close_db_connection, engine, run_migrations
from app.middleware.audit import AuditMiddleware
from app.middleware.audit_collector import AuditCollectorMiddleware
from app.middleware.audit_append_only import register_append_only_listeners
from app.middleware.logging import LoggingMiddleware
from app.middleware.usage_limit import UsageLimitMiddleware
from app.middleware.cache_middleware import CacheMiddleware
from app.middleware.demo_readonly import DemoReadOnlyMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routes import admin, admin_backup, analytics, appointments, audit_export, cache_admin, dicom, dicom_annotations, dicom_annotations_edit, dicom_annotations_export, dicom_context, dicom_volume, dicom_zip, docx_export, documents, dsar, export, export_async, export_excel, fhir_export, fhir_import, health, patients, payments, predictions, preferences, reports, sso, telegram, templates, totp, users, webhooks
from app.routes import websocket as websocket_route
from app.utils.logging import configure_logging
from app.webhooks import stripe as stripe_webhook
from app.webhooks import yookassa as yookassa_webhook
from app.auth import router as auth_router
from fastapi.staticfiles import StaticFiles

configure_logging()
logger = logging.getLogger(__name__)

# Initialise OpenTelemetry early (no-op unless OTEL_ENABLED + packages present).
try:
    from app.telemetry.setup import setup_telemetry

    setup_telemetry()
except Exception as exc:  # noqa: BLE001
    logger.warning("Telemetry setup error: %s", exc)

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
    shutdown_manager.register_handler("close_cache_redis", close_sync_binary_cache, timeout=5)
    shutdown_manager.register_handler("close_async_cache", close_async_cache, timeout=5)
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
    if settings.DICOM_ENABLED:
        Path(settings.DICOM_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    Path(settings.EXPORT_TEMP_DIR).mkdir(parents=True, exist_ok=True)
    if settings.STATIC_CACHE_ENABLED:
        Path(settings.STATIC_CACHE_DIR).mkdir(parents=True, exist_ok=True)
    if settings.BACKUP_ENABLED:
        Path(settings.BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    Path(settings.ENCRYPTION_KEY_PATH).parent.mkdir(parents=True, exist_ok=True)
    if settings.SCHEMA_INIT_ON_STARTUP and not settings.ALEMBIC_ENABLED:
        Base.metadata.create_all(bind=engine)
        run_migrations()
    bootstrap_system()

    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="medinsight")
    app.state.executor = executor
    _register_shutdown_handlers(executor)
    _install_signal_handlers()

    # Seed self-healing KB in background (Chroma ONNX download can take minutes on slow VPS).
    if settings.SELF_HEALING_ENABLED:

        def _seed_self_healing() -> None:
            try:
                from app.services.self_healing.vector_store import seed_knowledge_base

                imported, skipped = seed_knowledge_base()
                logger.info("Self-healing seed fixes: %d imported, %d skipped", imported, skipped)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Self-healing seed failed: %s", exc)

        executor.submit(_seed_self_healing)

    # Start the WebSocket Redis fan-in listener (cross-process event delivery).
    if settings.WEBSOCKET_ENABLED:
        from app.websocket.connection_manager import manager
        from app.websocket.events import run_event_listener

        ws_task = asyncio.create_task(run_event_listener(manager))
        app.state.ws_listener = ws_task
        shutdown_manager.register_handler("ws_listener", lambda: ws_task.cancel(), timeout=3)

    logger.info(
        "MedInsight v%s started. Storage: %s, DB dialect: %s",
        settings.APP_VERSION,
        settings.STORAGE_PATH,
        settings.DATABASE_URL.split("://", 1)[0],
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


def _localize_http_detail(detail: object) -> object:
    if detail == "There was an error parsing the body":
        return "Не удалось принять файл. Проверьте соединение и повторите загрузку."
    if detail == "Invalid HTTP request received.":
        return "Некорректный HTTP-запрос. Повторите попытку."
    return detail


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": _localize_http_detail(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    messages: list[str] = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", []) if part not in ("body",)]
        if "patient_id" in loc:
            messages.append("Выберите пациента")
            continue
        if "file" in loc:
            messages.append("Выберите DICOM-файл")
            continue
        field = ".".join(loc) if loc else "запрос"
        messages.append(f"{field}: {err.get('msg', 'ошибка валидации')}")
    detail: str | list[str] = messages[0] if len(messages) == 1 else messages
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    detail = str(exc) if settings.ENVIRONMENT != "production" else "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
register_append_only_listeners()
if settings.DEMO_MODE:
    app.add_middleware(DemoReadOnlyMiddleware)
if settings.AUDIT_SIGNING_ENABLED or settings.SIEM_EXPORT_ENABLED:
    app.add_middleware(AuditCollectorMiddleware)
else:
    app.add_middleware(AuditMiddleware)
if settings.REDIS_CACHE_ENABLED:
    app.add_middleware(CacheMiddleware)
app.add_middleware(UsageLimitMiddleware)
if settings.SECURITY_HEADERS_ENABLED:
    app.add_middleware(SecurityHeadersMiddleware)
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
app.include_router(sso.router, prefix="/api")
app.include_router(totp.router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(dicom.router, prefix="/api")
app.include_router(dicom_annotations.router, prefix="/api")
app.include_router(dicom_annotations_edit.router, prefix="/api")
app.include_router(dicom_annotations_export.router, prefix="/api")
app.include_router(dicom_zip.router, prefix="/api")
app.include_router(dicom_volume.router, prefix="/api")
app.include_router(dicom_context.dicom_router, prefix="/api")
app.include_router(dicom_context.analytics_router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(docx_export.router, prefix="/api")
app.include_router(export_async.router, prefix="/api")
app.include_router(export_excel.router, prefix="/api")
app.include_router(cache_admin.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(dsar.router, prefix="/api")
app.include_router(audit_export.router, prefix="/api")
app.include_router(admin_backup.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(webhooks.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(telegram.router, prefix="/api")
app.include_router(preferences.router, prefix="/api")
app.include_router(templates.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
if settings.APPOINTMENTS_ENABLED:
    app.include_router(appointments.router, prefix="/api")
if settings.FHIR_ENABLED:
    from app.routes.fhir import router as fhir_router

    app.include_router(fhir_router, prefix="/fhir")
    app.include_router(fhir_export.router, prefix="/api")
    app.include_router(fhir_import.router, prefix="/api")
# Inbound payment provider webhooks (no /api prefix, no auth — verified by signature)
app.include_router(stripe_webhook.router)
app.include_router(yookassa_webhook.router)
# Real-time WebSocket notifications (no /api prefix)
app.include_router(websocket_route.router)

# Instrument FastAPI + libraries for OpenTelemetry (no-op unless enabled).
try:
    from app.telemetry.setup import instrument_all

    instrument_all(app, engine)
except Exception as exc:  # noqa: BLE001
    logger.warning("Telemetry instrumentation error: %s", exc)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

docs_site_dir = Path(__file__).parent.parent / "site"
if docs_site_dir.is_dir():
    app.mount(
        "/help",
        StaticFiles(directory=str(docs_site_dir), html=True),
        name="help",
    )
    logger.info("Documentation site mounted at /help/")
else:
    logger.warning(
        "Documentation site not found at %s (mkdocs build skipped?)",
        docs_site_dir,
    )


@app.get("/metrics")
def metrics():
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)


@app.get("/reset-password")
def reset_password_page():
    return FileResponse(static_dir / "reset-password.html")


@app.get("/login")
def login_page():
    return FileResponse(static_dir / "login.html")


@app.get("/demo")
@app.get("/demo/")
def demo_landing_page():
    return FileResponse(static_dir / "demo" / "index.html")


@app.get("/demo/login")
def demo_login_redirect():
    return RedirectResponse(url="/login?demo=1", status_code=302)


@app.get("/verify-email")
def verify_email_page():
    return FileResponse(static_dir / "verify-email.html")


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


@app.get("/dicom")
def dicom_page():
    return FileResponse(static_dir / "dicom.html")


@app.get("/dicom/viewer/{study_uid}")
def dicom_viewer_page(study_uid: str):
    return FileResponse(static_dir / "dicom-viewer.html")


@app.get("/dicom/3d/{study_uid}")
def dicom_3d_viewer_page(study_uid: str):
    return FileResponse(static_dir / "pages" / "dicom-3d-viewer.html")


@app.get("/dicom/annotate/{study_uid}/{series_uid}/{frame_instance_uid}")
def dicom_annotate_page(study_uid: str, series_uid: str, frame_instance_uid: str):
    return FileResponse(static_dir / "dicom-annotate.html")


@app.get("/dicom/annotate-edit/{study_uid}/{series_uid}/{frame_instance_uid}")
def dicom_annotate_edit_page(study_uid: str, series_uid: str, frame_instance_uid: str):
    return FileResponse(static_dir / "dicom-annotate-edit.html")


@app.get("/subscription")
def subscription_page():
    return FileResponse(static_dir / "subscription.html")


@app.get("/appointments")
def appointments_page():
    return FileResponse(static_dir / "pages" / "appointments.html")


@app.get("/appointments/schedule")
def appointments_schedule_page():
    return FileResponse(static_dir / "pages" / "appointments.html")


def main() -> None:
    """Entry point for ``medinsight-api`` (Poetry script / CLI)."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
