"""FHIR R4/R4B REST API (FastAPI) — mounted at /fhir when FHIR_ENABLED=true."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Document, FhirMapping, Patient as PatientModel
from app.services.fhir.exporter import FhirExporter, _patient_dict
from app.services.fhir.fhir_models import Bundle, CapabilityStatement, Patient, fhir_dump
from app.services.fhir.importer import FhirImporter
from app.services.fhir.mapper import FhirMapper

logger = logging.getLogger(__name__)

router = APIRouter(tags=["fhir"])


def _resolve_patient(db: Session, fhir_id: str) -> PatientModel | None:
    try:
        uid = uuid.UUID(fhir_id)
        row = db.query(PatientModel).filter(PatientModel.public_id == uid).first()
        if row:
            return row
    except ValueError:
        pass
    mapping = (
        db.query(FhirMapping).filter(FhirMapping.resource_type == "Patient", FhirMapping.fhir_id == fhir_id).first()
    )
    if mapping:
        return db.get(PatientModel, mapping.medinsight_id)
    if fhir_id.isdigit():
        return db.get(PatientModel, int(fhir_id))
    return None


def _patient_ref_id(patient: str | None) -> str | None:
    if not patient:
        return None
    return patient.split("/")[-1] if "/" in patient else patient


def _json_response(resource: Any) -> dict:
    return fhir_dump(resource)


@router.get("/metadata")
def capability_statement() -> dict:
    cs = CapabilityStatement(
        status="active",
        date=datetime.utcnow().isoformat(),
        kind="instance",
        software={"name": settings.FHIR_PUBLISHER},
        implementation={"description": "MedInsight FHIR Server", "url": settings.FHIR_BASE_URL},
        fhirVersion="4.0.1" if settings.FHIR_VERSION in ("R4", "R4B") else "5.0.0",
        format=["json"],
        rest=[
            {
                "mode": "server",
                "resource": [
                    {"type": "Patient", "interaction": [{"code": c} for c in ("read", "search-type", "create", "update", "delete")]},
                    {"type": "Encounter", "interaction": [{"code": c} for c in ("read", "search-type")]},
                    {"type": "Observation", "interaction": [{"code": c} for c in ("read", "search-type")]},
                    {"type": "DiagnosticReport", "interaction": [{"code": c} for c in ("read", "search-type")]},
                    {"type": "ImagingStudy", "interaction": [{"code": c} for c in ("read", "search-type")]},
                    {"type": "Bundle", "interaction": [{"code": "transaction"}]},
                ],
            }
        ],
    )
    return _json_response(cs)


@router.get("/Patient/{patient_id}")
def read_patient(patient_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    row = _resolve_patient(db, patient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    return _json_response(FhirMapper.to_fhir_patient(_patient_dict(row)))


@router.get("/Patient")
def search_patient(
    db: Annotated[Session, Depends(get_db)],
    family: str | None = Query(None),
    given: str | None = Query(None),
    identifier: str | None = Query(None),
) -> dict:
    query = db.query(PatientModel)
    if family:
        query = query.filter(PatientModel.last_name.ilike(f"%{family}%"))
    if given:
        query = query.filter(PatientModel.first_name.ilike(f"%{given}%"))
    if identifier:
        mapping = (
            db.query(FhirMapping)
            .filter(FhirMapping.resource_type == "Patient", FhirMapping.fhir_id == identifier)
            .first()
        )
        if mapping:
            query = query.filter(PatientModel.id == mapping.medinsight_id)
        else:
            try:
                query = query.filter(PatientModel.public_id == uuid.UUID(identifier))
            except ValueError:
                query = query.filter(PatientModel.id == -1)
    rows = query.limit(50).all()
    bundle = FhirMapper.to_fhir_bundle([FhirMapper.to_fhir_patient(_patient_dict(p)) for p in rows], "searchset")
    return _json_response(bundle)


@router.post("/Patient", status_code=status.HTTP_201_CREATED)
def create_patient(resource: dict[str, Any], db: Annotated[Session, Depends(get_db)]) -> dict:
    patient = Patient(**resource)
    importer = FhirImporter(db)
    result = importer.import_patient(patient, tenant_id=1, user_id=1)
    patient.id = result["fhir_id"]
    return _json_response(patient)


@router.put("/Patient/{patient_id}")
def update_patient(patient_id: str, resource: dict[str, Any], db: Annotated[Session, Depends(get_db)]) -> dict:
    row = _resolve_patient(db, patient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient = Patient(**resource)
    data = FhirMapper.from_fhir_patient(patient)
    row.first_name = data["first_name"]
    row.last_name = data["last_name"]
    row.middle_name = data.get("middle_name")
    row.birth_date = data["birth_date"]
    row.gender = data["gender"]
    row.phone = data["phone"]
    row.email = data.get("email")
    db.commit()
    patient.id = patient_id
    return _json_response(patient)


@router.delete("/Patient/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(patient_id: str, db: Annotated[Session, Depends(get_db)]) -> Response:
    row = _resolve_patient(db, patient_id)
    if not row:
        raise HTTPException(status_code=404, detail="Patient not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/Encounter/{encounter_id}")
def read_encounter(encounter_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    mapping = db.query(FhirMapping).filter(FhirMapping.resource_type == "Encounter", FhirMapping.fhir_id == encounter_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Encounter not found")
    doc = db.get(Document, mapping.medinsight_id)
    patient = db.get(PatientModel, doc.patient_id)
    enc = FhirMapper.to_fhir_encounter(
        {
            "id": doc.id,
            "fhir_id": encounter_id,
            "patient_fhir_id": str(patient.public_id) if patient else doc.patient_id,
            "document_type": doc.document_type,
            "created_at": doc.created_at,
        }
    )
    return _json_response(enc)


@router.get("/Encounter")
def search_encounter(db: Annotated[Session, Depends(get_db)], patient: str | None = Query(None)) -> dict:
    query = db.query(Document).filter(Document.mime_type == "application/fhir+json")
    pid = _patient_ref_id(patient)
    if pid:
        prow = _resolve_patient(db, pid)
        if prow:
            query = query.filter(Document.patient_id == prow.id)
    resources = []
    for doc in query.limit(50).all():
        patient_row = db.get(PatientModel, doc.patient_id)
        resources.append(
            FhirMapper.to_fhir_encounter(
                {
                    "id": doc.id,
                    "patient_fhir_id": str(patient_row.public_id) if patient_row else doc.patient_id,
                    "document_type": doc.document_type,
                    "created_at": doc.created_at,
                }
            )
        )
    return _json_response(FhirMapper.to_fhir_bundle(resources, "searchset"))


@router.get("/Observation/{observation_id}")
def read_observation(observation_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    from app.models import Prediction

    mapping = (
        db.query(FhirMapping).filter(FhirMapping.resource_type == "Observation", FhirMapping.fhir_id == observation_id).first()
    )
    pred = db.get(Prediction, mapping.medinsight_id) if mapping else db.get(Prediction, int(observation_id)) if observation_id.isdigit() else None
    if not pred:
        raise HTTPException(status_code=404, detail="Observation not found")
    patient = db.get(PatientModel, pred.patient_id)
    obs = FhirMapper.to_fhir_observation(
        {
            "id": pred.id,
            "patient_fhir_id": str(patient.public_id) if patient else pred.patient_id,
            "type": pred.type,
            "prediction": pred.prediction,
            "created_at": pred.created_at,
        }
    )
    return _json_response(obs)


@router.get("/Observation")
def search_observation(db: Annotated[Session, Depends(get_db)], patient: str | None = Query(None)) -> dict:
    from app.models import Prediction

    query = db.query(Prediction)
    pid = _patient_ref_id(patient)
    if pid:
        prow = _resolve_patient(db, pid)
        if prow:
            query = query.filter(Prediction.patient_id == prow.id)
    resources = []
    for pred in query.limit(50).all():
        patient_row = db.get(PatientModel, pred.patient_id)
        resources.append(
            FhirMapper.to_fhir_observation(
                {
                    "id": pred.id,
                    "patient_fhir_id": str(patient_row.public_id) if patient_row else pred.patient_id,
                    "type": pred.type,
                    "prediction": pred.prediction,
                    "created_at": pred.created_at,
                }
            )
        )
    return _json_response(FhirMapper.to_fhir_bundle(resources, "searchset"))


@router.get("/DiagnosticReport/{report_id}")
def read_diagnostic_report(report_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    doc = None
    try:
        doc = db.query(Document).filter(Document.public_id == uuid.UUID(report_id)).first()
    except ValueError:
        if report_id.isdigit():
            doc = db.get(Document, int(report_id))
    if not doc:
        raise HTTPException(status_code=404, detail="DiagnosticReport not found")
    patient = db.get(PatientModel, doc.patient_id)
    report = FhirMapper.to_fhir_diagnostic_report(
        {
            "id": doc.id,
            "public_id": str(doc.public_id),
            "patient_fhir_id": str(patient.public_id) if patient else doc.patient_id,
            "document_type": doc.document_type,
            "status": doc.status,
            "parsed_data": doc.parsed_data,
            "created_at": doc.created_at,
            "parsed_at": doc.parsed_at,
        }
    )
    return _json_response(report)


@router.get("/DiagnosticReport")
def search_diagnostic_report(db: Annotated[Session, Depends(get_db)], patient: str | None = Query(None)) -> dict:
    query = db.query(Document)
    pid = _patient_ref_id(patient)
    if pid:
        prow = _resolve_patient(db, pid)
        if prow:
            query = query.filter(Document.patient_id == prow.id)
    resources = []
    for doc in query.limit(50).all():
        patient_row = db.get(PatientModel, doc.patient_id)
        resources.append(
            FhirMapper.to_fhir_diagnostic_report(
                {
                    "id": doc.id,
                    "public_id": str(doc.public_id),
                    "patient_fhir_id": str(patient_row.public_id) if patient_row else doc.patient_id,
                    "document_type": doc.document_type,
                    "status": doc.status,
                    "parsed_data": doc.parsed_data,
                    "created_at": doc.created_at,
                    "parsed_at": doc.parsed_at,
                }
            )
        )
    return _json_response(FhirMapper.to_fhir_bundle(resources, "searchset"))


@router.get("/ImagingStudy/{study_id}")
def read_imaging_study(study_id: str, db: Annotated[Session, Depends(get_db)]) -> dict:
    exporter = FhirExporter(db)
    try:
        return _json_response(exporter.export_dicom_study(study_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ImagingStudy")
def search_imaging_study(db: Annotated[Session, Depends(get_db)], patient: str | None = Query(None)) -> dict:
    from app.models import DicomStudy

    query = db.query(DicomStudy)
    pid = _patient_ref_id(patient)
    if pid:
        prow = _resolve_patient(db, pid)
        if prow:
            query = query.filter(DicomStudy.patient_id == prow.id)
    exporter = FhirExporter(db)
    resources = [exporter.export_dicom_study(s.study_uid) for s in query.limit(50).all()]
    return _json_response(FhirMapper.to_fhir_bundle(resources, "searchset"))


@router.post("/Bundle")
def import_bundle(payload: dict[str, Any], db: Annotated[Session, Depends(get_db)]) -> dict:
    bundle = Bundle(**payload)
    importer = FhirImporter(db)
    try:
        return importer.import_bundle(bundle, tenant_id=1, user_id=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
