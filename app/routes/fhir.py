"""FHIR R4 API via FHIRStarter — mounted at /fhir when FHIR_ENABLED=true."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fhir.resources.bundle import Bundle
from fhir.resources.diagnosticreport import DiagnosticReport
from fhir.resources.encounter import Encounter
from fhir.resources.imagingstudy import ImagingStudy
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient
from fhirstarter import FHIRProvider, FHIRStarter, InteractionContext
from fhirstarter.exceptions import FHIRResourceNotFoundError

from app.config import settings
from app.database import SessionLocal
from app.models import Document, FhirMapping, Patient as PatientModel
from app.services.fhir.exporter import FhirExporter, _patient_dict
from app.services.fhir.importer import FhirImporter
from app.services.fhir.mapper import FhirMapper
from app.services.list_queries import patients_scope

logger = logging.getLogger(__name__)

# FHIRStarter reads sequence from environment
os.environ.setdefault("FHIR_SEQUENCE", settings.FHIR_VERSION if settings.FHIR_VERSION != "R4" else "R4")

provider = FHIRProvider()
fhir_app = FHIRStarter()


def _resolve_patient(db, fhir_id: str) -> PatientModel | None:
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


def _patient_to_fhir(db, fhir_id: str) -> Patient:
    row = _resolve_patient(db, fhir_id)
    if not row:
        raise FHIRResourceNotFoundError
    return FhirMapper.to_fhir_patient(_patient_dict(row))


@provider.read(Patient)
async def patient_read(_context: InteractionContext, id_: str) -> Patient:
    db = SessionLocal()
    try:
        return _patient_to_fhir(db, id_)
    finally:
        db.close()


@provider.search_type(Patient)
async def patient_search(
    _context: InteractionContext,
    family: str | None = None,
    given: str | None = None,
    identifier: str | None = None,
) -> Bundle:
    db = SessionLocal()
    try:
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
        resources = [FhirMapper.to_fhir_patient(_patient_dict(p)) for p in rows]
        return FhirMapper.to_fhir_bundle(resources, "searchset")
    finally:
        db.close()


@provider.create(Patient)
async def patient_create(_context: InteractionContext, resource: Patient) -> Patient:
    db = SessionLocal()
    try:
        importer = FhirImporter(db)
        tenant_id = 1
        user_id = 1
        result = importer.import_patient(resource, tenant_id=tenant_id, user_id=user_id)
        resource.id = result["fhir_id"]
        return resource
    finally:
        db.close()


@provider.update(Patient)
async def patient_update(_context: InteractionContext, id_: str, resource: Patient) -> Patient:
    db = SessionLocal()
    try:
        row = _resolve_patient(db, id_)
        if not row:
            raise FHIRResourceNotFoundError
        data = FhirMapper.from_fhir_patient(resource)
        row.first_name = data["first_name"]
        row.last_name = data["last_name"]
        row.middle_name = data.get("middle_name")
        row.birth_date = data["birth_date"]
        row.gender = data["gender"]
        row.phone = data["phone"]
        row.email = data.get("email")
        db.commit()
        resource.id = id_
        return resource
    finally:
        db.close()


@provider.delete(Patient)
async def patient_delete(_context: InteractionContext, id_: str) -> None:
    db = SessionLocal()
    try:
        row = _resolve_patient(db, id_)
        if not row:
            raise FHIRResourceNotFoundError
        db.delete(row)
        db.commit()
    finally:
        db.close()


@provider.read(Encounter)
async def encounter_read(_context: InteractionContext, id_: str) -> Encounter:
    db = SessionLocal()
    try:
        mapping = db.query(FhirMapping).filter(FhirMapping.resource_type == "Encounter", FhirMapping.fhir_id == id_).first()
        if not mapping:
            raise FHIRResourceNotFoundError
        doc = db.get(Document, mapping.medinsight_id)
        patient = db.get(PatientModel, doc.patient_id)
        return FhirMapper.to_fhir_encounter(
            {
                "id": doc.id,
                "fhir_id": id_,
                "patient_fhir_id": str(patient.public_id) if patient else doc.patient_id,
                "document_type": doc.document_type,
                "created_at": doc.created_at,
                "updated_at": doc.parsed_at or doc.created_at,
            }
        )
    finally:
        db.close()


@provider.search_type(Encounter)
async def encounter_search(_context: InteractionContext, patient: str | None = None) -> Bundle:
    db = SessionLocal()
    try:
        query = db.query(Document).filter(Document.mime_type == "application/fhir+json")
        if patient:
            prow = _resolve_patient(db, patient.split("/")[-1] if "/" in patient else patient)
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
        return FhirMapper.to_fhir_bundle(resources, "searchset")
    finally:
        db.close()


@provider.read(Observation)
async def observation_read(_context: InteractionContext, id_: str) -> Observation:
    db = SessionLocal()
    try:
        from app.models import Prediction

        mapping = (
            db.query(FhirMapping).filter(FhirMapping.resource_type == "Observation", FhirMapping.fhir_id == id_).first()
        )
        pred = db.get(Prediction, mapping.medinsight_id) if mapping else db.get(Prediction, int(id_)) if id_.isdigit() else None
        if not pred:
            raise FHIRResourceNotFoundError
        patient = db.get(PatientModel, pred.patient_id)
        return FhirMapper.to_fhir_observation(
            {
                "id": pred.id,
                "patient_fhir_id": str(patient.public_id) if patient else pred.patient_id,
                "type": pred.type,
                "prediction": pred.prediction,
                "created_at": pred.created_at,
            }
        )
    finally:
        db.close()


@provider.search_type(Observation)
async def observation_search(_context: InteractionContext, patient: str | None = None) -> Bundle:
    db = SessionLocal()
    try:
        from app.models import Prediction

        query = db.query(Prediction)
        if patient:
            prow = _resolve_patient(db, patient.split("/")[-1] if "/" in patient else patient)
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
        return FhirMapper.to_fhir_bundle(resources, "searchset")
    finally:
        db.close()


@provider.read(DiagnosticReport)
async def diagnostic_report_read(_context: InteractionContext, id_: str) -> DiagnosticReport:
    db = SessionLocal()
    try:
        doc = None
        try:
            doc = db.query(Document).filter(Document.public_id == uuid.UUID(id_)).first()
        except ValueError:
            if id_.isdigit():
                doc = db.get(Document, int(id_))
        if not doc:
            raise FHIRResourceNotFoundError
        patient = db.get(PatientModel, doc.patient_id)
        return FhirMapper.to_fhir_diagnostic_report(
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
    finally:
        db.close()


@provider.search_type(DiagnosticReport)
async def diagnostic_report_search(_context: InteractionContext, patient: str | None = None) -> Bundle:
    db = SessionLocal()
    try:
        query = db.query(Document)
        if patient:
            prow = _resolve_patient(db, patient.split("/")[-1] if "/" in patient else patient)
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
        return FhirMapper.to_fhir_bundle(resources, "searchset")
    finally:
        db.close()


@provider.read(ImagingStudy)
async def imaging_study_read(_context: InteractionContext, id_: str) -> ImagingStudy:
    db = SessionLocal()
    try:
        from app.models import DicomStudy

        study = db.query(DicomStudy).filter(DicomStudy.study_uid == id_).first()
        if not study and id_.isdigit():
            study = db.get(DicomStudy, int(id_))
        if not study:
            raise FHIRResourceNotFoundError
        exporter = FhirExporter(db)
        return exporter.export_dicom_study(study.study_uid)
    finally:
        db.close()


@provider.search_type(ImagingStudy)
async def imaging_study_search(_context: InteractionContext, patient: str | None = None) -> Bundle:
    db = SessionLocal()
    try:
        from app.models import DicomStudy

        query = db.query(DicomStudy)
        if patient:
            prow = _resolve_patient(db, patient.split("/")[-1] if "/" in patient else patient)
            if prow:
                query = query.filter(DicomStudy.patient_id == prow.id)
        resources = []
        exporter = FhirExporter(db)
        for study in query.limit(50).all():
            resources.append(exporter.export_dicom_study(study.study_uid))
        return FhirMapper.to_fhir_bundle(resources, "searchset")
    finally:
        db.close()


fhir_app.add_providers(provider)
