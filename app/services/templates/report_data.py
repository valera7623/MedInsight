"""Build report context from MedInsight domain data."""

from __future__ import annotations

import base64
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import DicomStudy, Document, Patient, Prediction


_GENDER_LABELS = {"M": "Мужской", "F": "Женский", "O": "Другой"}


def _patient_dict(patient: Patient) -> dict[str, Any]:
    return {
        "id": patient.id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "middle_name": patient.middle_name,
        "birth_date": patient.birth_date.isoformat() if isinstance(patient.birth_date, date) else patient.birth_date,
        "gender": _GENDER_LABELS.get(patient.gender, patient.gender),
        "phone": patient.phone,
        "email": patient.email,
    }


def _full_name(patient: Patient) -> str:
    parts = [patient.last_name, patient.first_name]
    if patient.middle_name:
        parts.append(patient.middle_name)
    return " ".join(parts)


def _image_to_data_uri(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_clinical_context(db: Session, patient_id: int, extra: dict | None = None) -> dict[str, Any]:
    patient = db.get(Patient, patient_id)
    if not patient:
        raise ValueError(f"Patient {patient_id} not found")

    documents = (
        db.query(Document).filter(Document.patient_id == patient_id).order_by(Document.created_at.desc()).all()
    )
    diagnoses: list[str] = []
    medications: list[str] = []
    lab_results: list[dict] = []

    for doc in documents:
        if not doc.parsed_data:
            continue
        data = doc.parsed_data
        diagnoses.extend(data.get("diagnoses") or [])
        medications.extend(data.get("medications") or [])
        for lab in data.get("lab_results") or data.get("labs") or []:
            if isinstance(lab, dict):
                lab_results.append(
                    {
                        "name": lab.get("name", ""),
                        "value": lab.get("value", ""),
                        "reference": lab.get("reference", lab.get("unit", "")),
                    }
                )

    predictions = (
        db.query(Prediction).filter(Prediction.patient_id == patient_id).order_by(Prediction.created_at.desc()).all()
    )
    pred_rows = []
    for p in predictions:
        risk = None
        if isinstance(p.prediction, dict):
            risk = p.prediction.get("readmission_risk") or p.prediction.get("complication_risk")
            if risk is None and p.prediction:
                risk = next(iter(p.prediction.values()), None)
        if risk is not None:
            try:
                risk_pct = round(float(risk) * 100, 1) if float(risk) <= 1 else round(float(risk), 1)
            except (TypeError, ValueError):
                risk_pct = risk
            pred_rows.append({"type": p.type, "risk": risk_pct})

    ctx = {
        "generated_at": datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC"),
        "patient": _patient_dict(patient),
        "patient_name": _full_name(patient),
        "diagnoses": list(dict.fromkeys(diagnoses)),
        "medications": list(dict.fromkeys(medications)),
        "lab_results": lab_results,
        "predictions": pred_rows,
    }
    if extra:
        ctx.update(extra)
    return ctx


def build_dicom_context(db: Session, patient_id: int, study_uid: str | None = None, extra: dict | None = None) -> dict[str, Any]:
    patient = db.get(Patient, patient_id)
    if not patient:
        raise ValueError(f"Patient {patient_id} not found")

    query = db.query(DicomStudy).filter(DicomStudy.patient_id == patient_id)
    if study_uid:
        query = query.filter(DicomStudy.study_uid == study_uid)
    study = query.order_by(DicomStudy.created_at.desc()).first()
    if not study:
        raise ValueError("DICOM study not found")

    findings = study.radiology_findings or []
    if isinstance(findings, dict):
        findings = list(findings.values())

    images: list[str] = []
    try:
        from app.services.dicom_viewer import DicomViewerService

        viewer = DicomViewerService(db)
        thumb = viewer.get_thumbnail(study.study_uid)
        if thumb and thumb.startswith("/"):
            thumb_path = Path(".") / thumb.lstrip("/")
        else:
            thumb_path = Path(thumb) if thumb else None
        uri = _image_to_data_uri(thumb_path)
        if uri:
            images.append(uri)
    except Exception:
        pass

    ctx = {
        "generated_at": datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC"),
        "patient": _patient_dict(patient),
        "dicom_study": {
            "study_uid": study.study_uid,
            "study_description": study.study_description or "—",
            "modality": study.modality or "—",
            "body_part": study.body_part or "—",
            "num_series": study.num_series,
            "num_instances": study.num_instances,
            "impression": study.radiology_impression,
        },
        "findings": findings if isinstance(findings, list) else [str(findings)],
        "images": images,
    }
    if extra:
        ctx.update(extra)
    return ctx


def build_laboratory_context(db: Session, patient_id: int, extra: dict | None = None) -> dict[str, Any]:
    ctx = build_clinical_context(db, patient_id)
    ctx["title"] = "Результаты анализов"
    if extra:
        ctx.update(extra)
    return ctx


def build_prediction_context(db: Session, patient_id: int, extra: dict | None = None) -> dict[str, Any]:
    ctx = build_clinical_context(db, patient_id)
    ctx["title"] = "Прогноз рисков"
    if extra:
        ctx.update(extra)
    return ctx


def build_full_context(db: Session, patient_id: int, extra: dict | None = None) -> dict[str, Any]:
    ctx = build_clinical_context(db, patient_id)
    try:
        dicom_ctx = build_dicom_context(db, patient_id)
        ctx["dicom_study"] = dicom_ctx.get("dicom_study")
        ctx["findings"] = dicom_ctx.get("findings", [])
        ctx["images"] = dicom_ctx.get("images", [])
    except ValueError:
        ctx["dicom_study"] = None
        ctx["findings"] = []
        ctx["images"] = []
    ctx["title"] = "Полный клинический обзор"
    if extra:
        ctx.update(extra)
    return ctx


CONTEXT_BUILDERS = {
    "clinical": build_clinical_context,
    "laboratory": build_laboratory_context,
    "dicom": build_dicom_context,
    "prediction": build_prediction_context,
    "full": build_full_context,
}
