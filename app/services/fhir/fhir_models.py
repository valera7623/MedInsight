"""FHIR resource imports — R4 uses R4B sub-package (pydantic v2 compatible)."""

from __future__ import annotations

from app.config import settings

_pkg = "fhir.resources.R4B" if settings.FHIR_VERSION in ("R4", "R4B") else "fhir.resources"

if settings.FHIR_VERSION in ("R4", "R4B"):
    from fhir.resources.R4B.bundle import Bundle, BundleEntry, BundleEntryRequest
    from fhir.resources.R4B.capabilitystatement import CapabilityStatement
    from fhir.resources.R4B.codeableconcept import CodeableConcept
    from fhir.resources.R4B.coding import Coding
    from fhir.resources.R4B.contactpoint import ContactPoint
    from fhir.resources.R4B.diagnosticreport import DiagnosticReport
    from fhir.resources.R4B.encounter import Encounter
    from fhir.resources.R4B.humanname import HumanName
    from fhir.resources.R4B.identifier import Identifier
    from fhir.resources.R4B.imagingstudy import ImagingStudy, ImagingStudySeries
    from fhir.resources.R4B.meta import Meta
    from fhir.resources.R4B.observation import Observation
    from fhir.resources.R4B.patient import Patient
    from fhir.resources.R4B.period import Period
    from fhir.resources.R4B.quantity import Quantity
    from fhir.resources.R4B.reference import Reference
else:
    from fhir.resources.bundle import Bundle, BundleEntry, BundleEntryRequest
    from fhir.resources.capabilitystatement import CapabilityStatement
    from fhir.resources.codeableconcept import CodeableConcept
    from fhir.resources.coding import Coding
    from fhir.resources.contactpoint import ContactPoint
    from fhir.resources.diagnosticreport import DiagnosticReport
    from fhir.resources.encounter import Encounter
    from fhir.resources.humanname import HumanName
    from fhir.resources.identifier import Identifier
    from fhir.resources.imagingstudy import ImagingStudy, ImagingStudySeries
    from fhir.resources.meta import Meta
    from fhir.resources.observation import Observation
    from fhir.resources.patient import Patient
    from fhir.resources.period import Period
    from fhir.resources.quantity import Quantity
    from fhir.resources.reference import Reference


def fhir_dump(resource) -> dict:
    if hasattr(resource, "model_dump"):
        return resource.model_dump(mode="json", exclude_none=True)
    return resource.dict(exclude_none=True)
