"""Export MedInsight data as HL7 FHIR resources."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models import DicomStudy, Document, Patient as PatientModel, Prediction
from app.services.fhir.fhir_models import Bundle, Patient
from app.services.fhir.mapper import FhirMapper
from app.services.list_queries import dicom_studies_scope, documents_scope, patients_scope, predictions_scope


def _patient_dict(patient: PatientModel) -> dict[str, Any]:
    return {
        "id": patient.id,
        "public_id": str(patient.public_id),
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "middle_name": patient.middle_name,
        "birth_date": patient.birth_date,
        "gender": patient.gender,
        "phone": patient.phone,
        "email": patient.email,
        "created_at": patient.created_at,
        "updated_at": patient.updated_at,
    }


class FhirExporter:
    """Build FHIR resources from MedInsight database records."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.mapper = FhirMapper()

    def export_patient(self, patient_id: int) -> Patient:
        patient = self.db.get(PatientModel, patient_id)
        if not patient:
            raise ValueError(f"Patient {patient_id} not found")
        return self.mapper.to_fhir_patient(_patient_dict(patient))

    def export_all_patients(self, tenant_id: int, *, user, request_tenant_id: int | None) -> Bundle:
        rows = (
            patients_scope(self.db, user, tenant_id)
            .order_by(PatientModel.id.asc())
            .limit(settings.FHIR_EXPORT_MAX_RESOURCES)
            .all()
        )
        resources = [self.mapper.to_fhir_patient(_patient_dict(p)) for p in rows]
        return self.mapper.to_fhir_bundle(resources, "collection")

    def export_patient_bundle(self, patient_id: int) -> Bundle:
        patient = self.db.get(PatientModel, patient_id)
        if not patient:
            raise ValueError(f"Patient {patient_id} not found")
        pfhir = str(patient.public_id)
        resources: list[Any] = [self.mapper.to_fhir_patient(_patient_dict(patient))]

        for doc in self.db.query(Document).filter(Document.patient_id == patient_id).limit(500).all():
            resources.append(
                self.mapper.to_fhir_diagnostic_report(
                    {
                        "id": doc.id,
                        "public_id": str(doc.public_id),
                        "patient_fhir_id": pfhir,
                        "document_type": doc.document_type,
                        "status": doc.status,
                        "parsed_data": doc.parsed_data,
                        "created_at": doc.created_at,
                        "parsed_at": doc.parsed_at,
                    }
                )
            )
            resources.append(
                self.mapper.to_fhir_encounter(
                    {
                        "id": doc.id,
                        "patient_fhir_id": pfhir,
                        "document_type": doc.document_type,
                        "created_at": doc.created_at,
                        "updated_at": doc.parsed_at or doc.created_at,
                        "status": "finished",
                    }
                )
            )

        for pred in self.db.query(Prediction).filter(Prediction.patient_id == patient_id).limit(500).all():
            resources.append(
                self.mapper.to_fhir_observation(
                    {
                        "id": pred.id,
                        "patient_fhir_id": pfhir,
                        "type": pred.type,
                        "prediction": pred.prediction,
                        "created_at": pred.created_at,
                    }
                )
            )

        for study in self.db.query(DicomStudy).filter(DicomStudy.patient_id == patient_id).limit(200).all():
            resources.append(
                self.mapper.to_fhir_imaging_study(
                    {
                        "id": study.id,
                        "study_uid": study.study_uid,
                        "patient_fhir_id": pfhir,
                        "study_date": study.study_date,
                        "study_description": study.study_description,
                        "modality": study.modality,
                        "body_part": study.body_part,
                        "num_series": study.num_series,
                        "num_instances": study.num_instances,
                        "status": study.status,
                        "created_at": study.created_at,
                    }
                )
            )

        return self.mapper.to_fhir_bundle(resources, "collection")

    def export_dicom_study(self, study_uid: str) -> Any:
        study = self.db.query(DicomStudy).filter(DicomStudy.study_uid == study_uid).first()
        if not study:
            raise ValueError(f"DICOM study {study_uid} not found")
        patient = self.db.get(PatientModel, study.patient_id)
        return self.mapper.to_fhir_imaging_study(
            {
                "study_uid": study.study_uid,
                "patient_fhir_id": str(patient.public_id) if patient else study.patient_id,
                "study_date": study.study_date,
                "study_description": study.study_description,
                "modality": study.modality,
                "body_part": study.body_part,
                "num_series": study.num_series,
                "num_instances": study.num_instances,
                "status": study.status,
                "created_at": study.created_at,
            }
        )

    def export_by_date(
        self,
        from_date: datetime,
        to_date: datetime,
        *,
        user,
        tenant_id: int | None,
        resource_types: list[str] | None = None,
    ) -> Bundle:
        types = set(resource_types or ["Patient", "Observation", "DiagnosticReport", "ImagingStudy"])
        resources: list[Any] = []
        if "Patient" in types:
            for p in (
                patients_scope(self.db, user, tenant_id)
                .filter(PatientModel.created_at >= from_date, PatientModel.created_at <= to_date)
                .limit(settings.FHIR_EXPORT_BATCH_SIZE)
                .all()
            ):
                resources.append(self.mapper.to_fhir_patient(_patient_dict(p)))
        if "DiagnosticReport" in types:
            for doc in (
                documents_scope(self.db, user, tenant_id)
                .filter(Document.created_at >= from_date, Document.created_at <= to_date)
                .limit(settings.FHIR_EXPORT_BATCH_SIZE)
                .all()
            ):
                patient = self.db.get(PatientModel, doc.patient_id)
                resources.append(
                    self.mapper.to_fhir_diagnostic_report(
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
                )
        if "Observation" in types:
            for pred in (
                predictions_scope(self.db, user, tenant_id)
                .filter(Prediction.created_at >= from_date, Prediction.created_at <= to_date)
                .limit(settings.FHIR_EXPORT_BATCH_SIZE)
                .all()
            ):
                patient = self.db.get(PatientModel, pred.patient_id)
                resources.append(
                    self.mapper.to_fhir_observation(
                        {
                            "id": pred.id,
                            "patient_fhir_id": str(patient.public_id) if patient else pred.patient_id,
                            "type": pred.type,
                            "prediction": pred.prediction,
                            "created_at": pred.created_at,
                        }
                    )
                )
        if "ImagingStudy" in types:
            for study in (
                dicom_studies_scope(self.db, user, tenant_id)
                .filter(DicomStudy.created_at >= from_date, DicomStudy.created_at <= to_date)
                .limit(settings.FHIR_EXPORT_BATCH_SIZE)
                .all()
            ):
                patient = self.db.get(PatientModel, study.patient_id)
                resources.append(
                    self.mapper.to_fhir_imaging_study(
                        {
                            "study_uid": study.study_uid,
                            "patient_fhir_id": str(patient.public_id) if patient else study.patient_id,
                            "study_date": study.study_date,
                            "study_description": study.study_description,
                            "modality": study.modality,
                            "body_part": study.body_part,
                            "num_series": study.num_series,
                            "num_instances": study.num_instances,
                            "status": study.status,
                            "created_at": study.created_at,
                        }
                    )
                )
        if len(resources) > settings.FHIR_EXPORT_MAX_RESOURCES:
            resources = resources[: settings.FHIR_EXPORT_MAX_RESOURCES]
        return self.mapper.to_fhir_bundle(resources, "collection")
