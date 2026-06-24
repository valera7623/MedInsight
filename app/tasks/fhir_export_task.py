"""Async FHIR batch export Celery tasks."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.database import SessionLocal
from app.models import User
from app.services.fhir.exporter import FhirExporter
from app.services.fhir.fhir_models import fhir_dump
from app.services.fhir.smart_on_fhir import SmartOnFhirClient
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_EXPORT_DIR = Path(settings.STORAGE_PATH) / "fhir_exports"


@celery_app.task(bind=True, name="app.tasks.fhir_export_task.export_fhir_batch")
def export_fhir_batch(self, tenant_id: int, resource_types: list[str], since_iso: str) -> str:
    if not settings.FHIR_ENABLED:
        return "skipped: FHIR disabled"
    since = datetime.fromisoformat(since_iso)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.tenant_id == tenant_id, User.role == "admin").first()
        if not user:
            user = db.query(User).filter(User.role == "super_admin").first()
        exporter = FhirExporter(db)
        bundle = exporter.export_by_date(
            since,
            datetime.utcnow(),
            user=user,
            tenant_id=tenant_id,
            resource_types=resource_types,
        )
        _EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        out = _EXPORT_DIR / f"fhir_batch_{tenant_id}_{self.request.id}.json"
        out.write_text(json.dumps(fhir_dump(bundle), default=str), encoding="utf-8")
        logger.info("FHIR batch export written to %s", out)
        return str(out)
    finally:
        db.close()


@celery_app.task(name="app.tasks.fhir_export_task.export_to_external_ehr")
def export_to_external_ehr(patient_id: int, ehr_config: dict) -> dict:
    if not settings.FHIR_ENABLED:
        return {"status": "skipped", "reason": "FHIR disabled"}
    db = SessionLocal()
    try:
        exporter = FhirExporter(db)
        bundle = exporter.export_patient_bundle(patient_id)
        client = SmartOnFhirClient(
            authorization_url=ehr_config.get("authorization_url"),
            token_url=ehr_config.get("token_url"),
            client_id=ehr_config.get("client_id"),
            client_secret=ehr_config.get("client_secret"),
            fhir_base_url=ehr_config.get("fhir_base_url"),
        )
        pushed = []
        for entry in bundle.entry or []:
            if entry.resource:
                resource = fhir_dump(entry.resource)
                pushed.append(client.push_resource(resource))
        return {"status": "ok", "patient_id": patient_id, "resources_pushed": len(pushed)}
    except Exception as exc:
        logger.exception("EHR export failed: %s", exc)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
