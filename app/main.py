import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, bootstrap_system, engine, run_migrations
from app.middleware.audit import AuditMiddleware
from app.routes import admin, analytics, documents, export, patients, predictions, users
from app.auth import router as auth_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="MedInsight", description="Clinical analytics platform", version="0.3.0")

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info("%s %s -> %s (%.1fms)", request.method, request.url.path, response.status_code, duration_ms)
    return response


@app.on_event("startup")
def on_startup():
    Path(settings.STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    Path(settings.STORAGE_PATH, "encrypted").mkdir(parents=True, exist_ok=True)
    Path(settings.ENCRYPTION_KEY_PATH).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    run_migrations()
    bootstrap_system()
    logger.info(
        "MedInsight v0.3 started. Storage: %s, DB: %s",
        settings.STORAGE_PATH,
        settings.DATABASE_URL,
    )


app.include_router(auth_router, prefix="/api")
app.include_router(patients.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(users.router, prefix="/api")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


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


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.3.0"}
