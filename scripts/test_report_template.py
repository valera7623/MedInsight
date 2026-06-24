#!/usr/bin/env python3
"""Test PDF report template: seed template, generate report, verify PDF."""

from __future__ import annotations

import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import Department, Patient, Tenant, User  # noqa: E402
from app.services.pdf_generator import PdfGenerator  # noqa: E402
from app.services.templates.report_data import build_clinical_context  # noqa: E402
from app.services.templates.template_manager import TemplateManager  # noqa: E402
from app.services.templates.template_renderer import TemplateRenderer  # noqa: E402
from app.tasks.report_task import _generate_report_sync  # noqa: E402
from app.models import GeneratedReport  # noqa: E402


def _ensure_fixtures(db) -> tuple[int, int, int]:
    tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
    if not tenant:
        tenant = Tenant(name="Report Test Clinic", subdomain=f"rpt-{uuid.uuid4().hex[:6]}", settings={}, is_active=True)
        db.add(tenant)
        db.flush()
    dept = db.query(Department).filter(Department.tenant_id == tenant.id).first()
    if not dept:
        dept = Department(tenant_id=tenant.id, name="Therapy")
        db.add(dept)
        db.flush()
    user = db.query(User).filter(User.tenant_id == tenant.id, User.role == "admin").first()
    if not user:
        user = User(
            tenant_id=tenant.id,
            email=f"report-test-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="x",
            full_name="Report Tester",
            role="admin",
            email_verified=True,
        )
        db.add(user)
        db.flush()
    patient = (
        db.query(Patient)
        .filter(Patient.tenant_id == tenant.id, Patient.first_name == "ReportTest")
        .first()
    )
    if not patient:
        patient = Patient(
            tenant_id=tenant.id,
            user_id=user.id,
            department_id=dept.id,
            first_name="ReportTest",
            last_name="Patient",
            birth_date=date(1990, 5, 20),
            gender="M",
            phone="+79001112233",
        )
        db.add(patient)
        db.flush()
    db.commit()
    return tenant.id, user.id, patient.id


def main() -> int:
    print("=== MedInsight Report Template Test ===")
    print(f"REPORTS_STORAGE_PATH={settings.REPORTS_STORAGE_PATH}")

    db = SessionLocal()
    try:
        tenant_id, user_id, patient_id = _ensure_fixtures(db)
        mgr = TemplateManager(db)
        templates = mgr.seed_defaults(tenant_id, user_id)
        clinical = next(t for t in templates if t.template_type == "clinical")
        print(f"Template: id={clinical.id} name={clinical.name}")

        context = build_clinical_context(db, patient_id)
        renderer = TemplateRenderer(db)
        html = renderer.render_template(clinical.id, context)
        assert "<html" in html.lower() and "ReportTest" in html or "Patient" in html
        print(f"HTML rendered: {len(html)} bytes")

        pdf = renderer.render_to_pdf(clinical.id, context)
        meta = PdfGenerator.get_pdf_metadata(pdf)
        print(f"PDF: {meta['pages']} page(s), {meta['size_bytes']} bytes")
        assert meta["pages"] >= 1

        report = GeneratedReport(
            template_id=clinical.id,
            patient_id=patient_id,
            user_id=user_id,
            tenant_id=tenant_id,
            report_data=context,
            status="pending",
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        result = _generate_report_sync(report.id, {})
        print(f"Async generation result: {result}")
        db.refresh(report)
        assert report.status == "completed"
        assert report.pdf_path and Path(report.pdf_path).exists()
        print(f"PDF saved: {report.pdf_path}")
        print("RESULT: PASS")
        return 0
    except Exception as exc:
        print(f"RESULT: FAIL — {exc}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
