"""FHIR mapper unit tests."""

from app.services.fhir.mapper import FhirMapper


def test_imaging_study_series_body_site_uses_coding():
    study = FhirMapper.to_fhir_imaging_study(
        {
            "id": 1,
            "study_uid": "1.2.3.4",
            "patient_fhir_id": "p-1",
            "modality": "MR",
            "body_part": "BRAIN",
            "num_series": 1,
            "num_instances": 21,
            "status": "ready",
        }
    )
    assert study.series
    body_site = study.series[0].bodySite
    assert body_site is not None
    assert body_site.display == "BRAIN"
