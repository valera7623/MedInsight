"""Map MedInsight domain objects to/from HL7 FHIR R4/R4B resources."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from app.config import settings
from app.services.fhir.fhir_models import (
    Bundle,
    BundleEntry,
    BundleEntryRequest,
    CodeableConcept,
    Coding,
    ContactPoint,
    DiagnosticReport,
    Encounter,
    HumanName,
    Identifier,
    ImagingStudy,
    ImagingStudySeries,
    Meta,
    Observation,
    Patient,
    Period,
    Quantity,
    Reference,
)

_GENDER_TO_FHIR = {"M": "male", "F": "female", "O": "other"}
_GENDER_FROM_FHIR = {v: k for k, v in _GENDER_TO_FHIR.items()}
_SYSTEM_MEDINSIGHT = "https://medinsight.com/fhir"


def _meta() -> Meta:
    return Meta(versionId="1", lastUpdated=datetime.utcnow())


def _patient_ref(patient_id: str | int) -> Reference:
    return Reference(reference=f"Patient/{patient_id}")


class FhirMapper:
    """Bidirectional mapper between MedInsight records and FHIR resources."""

    @staticmethod
    def fhir_id_for_patient(patient: dict[str, Any]) -> str:
        return str(patient.get("public_id") or patient.get("id"))

    @classmethod
    def to_fhir_patient(cls, medinsight_patient: dict[str, Any]) -> Patient:
        pid = cls.fhir_id_for_patient(medinsight_patient)
        names = [
            HumanName(
                family=medinsight_patient.get("last_name"),
                given=[n for n in [medinsight_patient.get("first_name"), medinsight_patient.get("middle_name")] if n],
            )
        ]
        telecom: list[ContactPoint] = []
        if medinsight_patient.get("phone"):
            telecom.append(ContactPoint(system="phone", value=medinsight_patient["phone"]))
        if medinsight_patient.get("email"):
            telecom.append(ContactPoint(system="email", value=medinsight_patient["email"]))
        identifiers = [Identifier(system=f"{_SYSTEM_MEDINSIGHT}/patient", value=pid)]
        if medinsight_patient.get("id"):
            identifiers.append(
                Identifier(system=f"{_SYSTEM_MEDINSIGHT}/internal-id", value=str(medinsight_patient["id"]))
            )
        birth = medinsight_patient.get("birth_date")
        if isinstance(birth, datetime):
            birth = birth.date()
        return Patient(
            id=pid,
            meta=_meta(),
            identifier=identifiers,
            active=True,
            name=names,
            telecom=telecom or None,
            gender=_GENDER_TO_FHIR.get(medinsight_patient.get("gender", "O"), "unknown"),
            birthDate=birth,
        )

    @classmethod
    def from_fhir_patient(cls, fhir_patient: Patient) -> dict[str, Any]:
        family = given = middle = None
        if fhir_patient.name:
            hn = fhir_patient.name[0]
            family = hn.family
            if hn.given:
                given = hn.given[0]
                if len(hn.given) > 1:
                    middle = hn.given[1]
        phone = email = None
        for cp in fhir_patient.telecom or []:
            if cp.system == "phone" and cp.value:
                phone = cp.value
            if cp.system == "email" and cp.value:
                email = cp.value
        birth_date = fhir_patient.birthDate
        if isinstance(birth_date, str):
            birth_date = date.fromisoformat(birth_date)
        gender = _GENDER_FROM_FHIR.get(fhir_patient.gender or "unknown", "O")
        return {
            "first_name": given or "Unknown",
            "last_name": family or "Unknown",
            "middle_name": middle,
            "birth_date": birth_date or date(1900, 1, 1),
            "gender": gender,
            "phone": phone or "0000000000",
            "email": email,
            "fhir_id": fhir_patient.id,
        }

    @classmethod
    def to_fhir_encounter(cls, medinsight_encounter: dict[str, Any]) -> Encounter:
        eid = str(medinsight_encounter.get("fhir_id") or medinsight_encounter.get("id"))
        patient_id = str(
            medinsight_encounter.get("patient_fhir_id")
            or medinsight_encounter.get("patient_public_id")
            or medinsight_encounter.get("patient_id")
        )
        start = medinsight_encounter.get("start") or medinsight_encounter.get("created_at")
        end = medinsight_encounter.get("end") or medinsight_encounter.get("updated_at")
        period = Period(start=start, end=end) if start or end else None
        enc_class = Coding(system="http://terminology.hl7.org/CodeSystem/v3-ActCode", code="AMB", display="ambulatory")
        return Encounter(
            id=eid,
            meta=_meta(),
            status=medinsight_encounter.get("status", "finished"),
            class_fhir=enc_class,
            subject=_patient_ref(patient_id),
            period=period,
            type=[
                CodeableConcept(
                    text=medinsight_encounter.get("encounter_type") or medinsight_encounter.get("document_type")
                )
            ]
            if medinsight_encounter.get("encounter_type") or medinsight_encounter.get("document_type")
            else None,
        )

    @classmethod
    def to_fhir_observation(cls, medinsight_prediction: dict[str, Any]) -> Observation:
        oid = str(medinsight_prediction.get("fhir_id") or medinsight_prediction.get("id"))
        patient_id = str(
            medinsight_prediction.get("patient_fhir_id")
            or medinsight_prediction.get("patient_public_id")
            or medinsight_prediction.get("patient_id")
        )
        pred_type = medinsight_prediction.get("type", "readmission")
        prediction = medinsight_prediction.get("prediction") or {}
        value = prediction.get("readmission_risk") or prediction.get("complication_risk")
        if value is None and isinstance(prediction, dict):
            value = next(iter(prediction.values()), None)
        quantity = Quantity(value=float(value), unit="probability") if value is not None else None
        return Observation(
            id=oid,
            meta=_meta(),
            status="final",
            category=[
                CodeableConcept(
                    coding=[
                        Coding(
                            system="http://terminology.hl7.org/CodeSystem/observation-category",
                            code="survey",
                        )
                    ]
                )
            ],
            code=CodeableConcept(
                coding=[
                    Coding(
                        system=f"{_SYSTEM_MEDINSIGHT}/prediction-type",
                        code=pred_type,
                        display=f"MedInsight {pred_type} prediction",
                    )
                ]
            ),
            subject=_patient_ref(patient_id),
            effectiveDateTime=medinsight_prediction.get("created_at"),
            valueQuantity=quantity,
        )

    @classmethod
    def to_fhir_diagnostic_report(cls, medinsight_document: dict[str, Any]) -> DiagnosticReport:
        did = str(
            medinsight_document.get("fhir_id")
            or medinsight_document.get("public_id")
            or medinsight_document.get("id")
        )
        patient_id = str(
            medinsight_document.get("patient_fhir_id")
            or medinsight_document.get("patient_public_id")
            or medinsight_document.get("patient_id")
        )
        parsed = medinsight_document.get("parsed_data") or {}
        conclusion = None
        if isinstance(parsed, dict):
            conclusion = parsed.get("summary") or parsed.get("conclusion") or str(parsed)[:2000]
        return DiagnosticReport(
            id=did,
            meta=_meta(),
            status="final" if medinsight_document.get("status") == "parsed" else "partial",
            category=[
                CodeableConcept(
                    coding=[
                        Coding(
                            system="http://terminology.hl7.org/CodeSystem/v2-0074",
                            code="LAB" if medinsight_document.get("document_type") == "lab" else "OTH",
                        )
                    ]
                )
            ],
            code=CodeableConcept(text=medinsight_document.get("document_type") or "clinical-document"),
            subject=_patient_ref(patient_id),
            effectiveDateTime=medinsight_document.get("parsed_at") or medinsight_document.get("created_at"),
            issued=medinsight_document.get("created_at"),
            conclusion=conclusion,
        )

    @classmethod
    def to_fhir_imaging_study(cls, dicom_study: dict[str, Any]) -> ImagingStudy:
        sid = dicom_study.get("study_uid") or str(dicom_study.get("id"))
        patient_id = str(
            dicom_study.get("patient_fhir_id")
            or dicom_study.get("patient_public_id")
            or dicom_study.get("patient_id")
        )
        series = []
        if dicom_study.get("num_series"):
            series.append(
                ImagingStudySeries(
                    uid=f"{sid}.1",
                    modality=Coding(
                        system="http://dicom.nema.org/resources/ontology/DCM",
                        code=dicom_study.get("modality") or "OT",
                    )
                    if dicom_study.get("modality")
                    else None,
                    numberOfInstances=dicom_study.get("num_instances"),
                    bodySite=CodeableConcept(text=dicom_study.get("body_part")) if dicom_study.get("body_part") else None,
                )
            )
        return ImagingStudy(
            id=sid,
            meta=_meta(),
            status="available" if dicom_study.get("status") == "processed" else "registered",
            subject=_patient_ref(patient_id),
            started=dicom_study.get("study_date") or dicom_study.get("created_at"),
            description=dicom_study.get("study_description"),
            numberOfSeries=dicom_study.get("num_series"),
            numberOfInstances=dicom_study.get("num_instances"),
            series=series or None,
            identifier=[Identifier(system="urn:dicom:uid", value=f"urn:oid:{sid}")],
        )

    @classmethod
    def to_fhir_bundle(cls, resources: list[Any], bundle_type: str = "collection") -> Bundle:
        entries = []
        for resource in resources:
            rtype = resource.resource_type if hasattr(resource, "resource_type") else resource.__class__.__name__
            rid = getattr(resource, "id", None)
            entries.append(
                BundleEntry(
                    fullUrl=f"{settings.FHIR_BASE_URL}/{rtype}/{rid}" if rid else None,
                    resource=resource,
                )
            )
        return Bundle(
            id=str(uuid.uuid4()),
            meta=_meta(),
            type=bundle_type,
            timestamp=datetime.utcnow(),
            entry=entries,
        )
