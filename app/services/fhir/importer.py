"""Import FHIR resources into MedInsight database."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.services.fhir.fhir_models import Bundle, Encounter, Patient
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Department, Document, FhirMapping, Patient as PatientModel, Prediction
from app.services.fhir.mapper import FhirMapper

logger = logging.getLogger(__name__)


class FhirImporter:
    """Persist FHIR resources as MedInsight domain records."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.mapper = FhirMapper()

    def _upsert_mapping(self, resource_type: str, medinsight_id: int, fhir_id: str) -> FhirMapping:
        row = (
            self.db.query(FhirMapping)
            .filter(FhirMapping.resource_type == resource_type, FhirMapping.medinsight_id == medinsight_id)
            .first()
        )
        if row:
            row.fhir_id = fhir_id
            row.fhir_version = settings.FHIR_VERSION
            return row
        row = FhirMapping(
            resource_type=resource_type,
            medinsight_id=medinsight_id,
            fhir_id=fhir_id,
            fhir_version=settings.FHIR_VERSION,
        )
        self.db.add(row)
        return row

    def _default_department_id(self, tenant_id: int) -> int:
        dept = (
            self.db.query(Department)
            .filter(Department.tenant_id == tenant_id)
            .order_by(Department.id.asc())
            .first()
        )
        if not dept:
            raise ValueError(f"No department found for tenant {tenant_id}")
        return dept.id

    def import_patient(self, fhir_patient: Patient, *, tenant_id: int, user_id: int) -> dict[str, Any]:
        data = self.mapper.from_fhir_patient(fhir_patient)
        fhir_id = fhir_patient.id or str(uuid.uuid4())
        existing = None
        if fhir_patient.id:
            mapping = (
                self.db.query(FhirMapping)
                .filter(FhirMapping.resource_type == "Patient", FhirMapping.fhir_id == fhir_id)
                .first()
            )
            if mapping:
                existing = self.db.get(PatientModel, mapping.medinsight_id)
        if existing:
            existing.first_name = data["first_name"]
            existing.last_name = data["last_name"]
            existing.middle_name = data.get("middle_name")
            existing.birth_date = data["birth_date"]
            existing.gender = data["gender"]
            existing.phone = data["phone"]
            existing.email = data.get("email")
            patient = existing
        else:
            patient = PatientModel(
                tenant_id=tenant_id,
                user_id=user_id,
                department_id=self._default_department_id(tenant_id),
                first_name=data["first_name"],
                last_name=data["last_name"],
                middle_name=data.get("middle_name"),
                birth_date=data["birth_date"],
                gender=data["gender"],
                phone=data["phone"],
                email=data.get("email"),
            )
            if fhir_patient.id:
                try:
                    patient.public_id = uuid.UUID(fhir_id)
                except ValueError:
                    pass
            self.db.add(patient)
            self.db.flush()
        self._upsert_mapping("Patient", patient.id, fhir_id)
        self.db.commit()
        self.db.refresh(patient)
        return {"id": patient.id, "public_id": str(patient.public_id), "fhir_id": fhir_id}

    def import_encounter(self, fhir_encounter: Encounter, patient_id: int) -> dict[str, Any]:
        eid = fhir_encounter.id or str(uuid.uuid4())
        doc = Document(
            tenant_id=self.db.get(PatientModel, patient_id).tenant_id,
            patient_id=patient_id,
            user_id=self.db.get(PatientModel, patient_id).user_id,
            filename=f"encounter-{eid}.fhir",
            file_path="",
            file_size=0,
            mime_type="application/fhir+json",
            document_type=fhir_encounter.type[0].text if fhir_encounter.type else "encounter",
            status="parsed",
            parsed_data={"fhir_encounter": fhir_encounter.model_dump(mode="json") if hasattr(fhir_encounter, "model_dump") else fhir_encounter.dict()},
        )
        self.db.add(doc)
        self.db.flush()
        self._upsert_mapping("Encounter", doc.id, eid)
        self.db.commit()
        return {"id": doc.id, "fhir_id": eid, "patient_id": patient_id}

    def validate_bundle(self, fhir_bundle: Bundle) -> bool:
        if fhir_bundle.type not in ("collection", "transaction", "batch", "document"):
            return False
        if not fhir_bundle.entry:
            return False
        for entry in fhir_bundle.entry:
            if entry.resource is None:
                return False
        return True

    def import_bundle(
        self,
        fhir_bundle: Bundle,
        *,
        tenant_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        if not self.validate_bundle(fhir_bundle):
            raise ValueError("Invalid FHIR Bundle")
        results: dict[str, list] = {"Patient": [], "Encounter": [], "Observation": [], "errors": []}
        patient_id_map: dict[str, int] = {}
        for entry in fhir_bundle.entry or []:
            resource = entry.resource
            try:
                if resource.resource_type == "Patient":
                    res = self.import_patient(resource, tenant_id=tenant_id, user_id=user_id)
                    results["Patient"].append(res)
                    patient_id_map[res["fhir_id"]] = res["id"]
                elif resource.resource_type == "Encounter":
                    sub_ref = resource.subject.reference if resource.subject else ""
                    pid_fhir = sub_ref.split("/")[-1] if sub_ref else None
                    pid = patient_id_map.get(pid_fhir or "")
                    if not pid:
                        results["errors"].append(f"Encounter {resource.id}: patient not found")
                        continue
                    results["Encounter"].append(self.import_encounter(resource, pid))
                elif resource.resource_type == "Observation":
                    sub_ref = resource.subject.reference if resource.subject else ""
                    pid_fhir = sub_ref.split("/")[-1] if sub_ref else None
                    pid = patient_id_map.get(pid_fhir or "")
                    if not pid:
                        results["errors"].append(f"Observation {resource.id}: patient not found")
                        continue
                    patient = self.db.get(PatientModel, pid)
                    pred = Prediction(
                        tenant_id=patient.tenant_id,
                        patient_id=pid,
                        user_id=user_id,
                        type="fhir_import",
                        features={},
                        prediction={"value": resource.valueQuantity.value if resource.valueQuantity else None},
                        probabilities={},
                        confidence_score=0.5,
                    )
                    self.db.add(pred)
                    self.db.flush()
                    self._upsert_mapping("Observation", pred.id, resource.id or str(pred.id))
                    results.setdefault("Observation", []).append({"id": pred.id, "fhir_id": resource.id})
            except Exception as exc:
                logger.warning("Bundle import error for %s: %s", getattr(resource, "id", "?"), exc)
                results["errors"].append(str(exc))
        self.db.commit()
        return results
