import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models import DicomStudy, Document, Patient, Prediction
from app.prompts.clinical_prompts import build_gpt_clinical_prompt
from app.prompts.dicom_prompts import (
    SYSTEM_PROMPT_DICOM,
    build_gpt_user_prompt,
    compare_with_guidelines,
)
from app.services.openai_client import OpenAIClientError, chat_completion_json
from app.services.extractor import consolidate_diagnosis_labels, diagnoses_from_parsed_data
from app.utils.tracing import trace_span

logger = logging.getLogger(__name__)

GENDER_LABELS = {"M": "мужской", "F": "женский", "O": "другой"}


def _calculate_age(birth_date: date) -> int:
    today = date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _lab_results_from_documents(documents: list[Document]) -> dict:
    labs: dict = {}
    for doc in documents:
        if not doc.parsed_data:
            continue
        doc_labs = doc.parsed_data.get("lab_results") or doc.parsed_data.get("labs") or {}
        if isinstance(doc_labs, dict):
            labs.update(doc_labs)
    return labs


def _collect_dicom_bundle(db: Session, patient_id: int, tenant_id: int | None = None) -> dict:
    """Aggregate DICOM metadata, findings and measurements for a patient."""
    query = db.query(DicomStudy).filter(
        DicomStudy.patient_id == patient_id,
        DicomStudy.status == "ready",
    )
    if tenant_id is not None:
        query = query.filter(DicomStudy.tenant_id == tenant_id)
    studies = query.order_by(DicomStudy.study_date.desc().nullslast()).all()

    bundle: dict = {
        "study_count": len(studies),
        "studies": [],
        "findings": [],
        "impressions": [],
        "measurements": {"organs": {}, "tumors": [], "bones": [], "vessels": []},
        "sources": [],
        "guideline_alignment": [],
    }

    for study in studies:
        bundle["studies"].append(
            {
                "study_uid": study.study_uid,
                "modality": study.modality,
                "body_part": study.body_part,
                "study_description": study.study_description,
                "study_date": study.study_date.isoformat() if study.study_date else None,
            }
        )
        bundle["sources"].append(
            {
                "study_uid": study.study_uid,
                "modality": study.modality,
                "body_part": study.body_part,
                "has_clinical_context": bool(study.clinical_context),
                "has_annotations": bool(study.extracted_measurements),
            }
        )

        findings = study.radiology_findings or []
        if not findings and study.clinical_context:
            try:
                ctx = json.loads(study.clinical_context)
                findings = ctx.get("findings", [])
            except json.JSONDecodeError:
                pass
        bundle["findings"].extend(findings)

        impression = study.radiology_impression
        if not impression and study.clinical_context:
            try:
                ctx = json.loads(study.clinical_context)
                impression = ctx.get("impression")
            except json.JSONDecodeError:
                pass
        if impression:
            bundle["impressions"].append(impression)

        if study.extracted_measurements:
            for key in ("organs", "tumors", "bones", "vessels"):
                val = study.extracted_measurements.get(key)
                if isinstance(val, dict):
                    bundle["measurements"][key].update(val)
                elif isinstance(val, list):
                    bundle["measurements"][key].extend(val)

        alignment = compare_with_guidelines(study.modality, study.body_part, findings)
        bundle["guideline_alignment"].extend(alignment)

    bundle["findings"] = list(dict.fromkeys(bundle["findings"]))[:30]
    bundle["impressions"] = list(dict.fromkeys(bundle["impressions"]))[:10]
    return bundle


def _collect_patient_features(db: Session, patient_id: int, user_id: int, tenant_id: int | None = None) -> dict:
    """Collect clinical features for ML/GPT. user_id is the analyst, not the patient creator."""
    query = db.query(Patient).filter(Patient.id == patient_id)
    if tenant_id is not None:
        query = query.filter(Patient.tenant_id == tenant_id)
    patient = query.first()
    if not patient:
        raise ValueError("Patient not found")

    doc_query = db.query(Document).filter(Document.patient_id == patient_id)
    if tenant_id is not None:
        doc_query = doc_query.filter(Document.tenant_id == tenant_id)
    documents = doc_query.all()

    diagnoses: set[str] = set()
    anamnesis: set[str] = set()
    operations: set[str] = set()
    imaging_conclusions: set[str] = set()
    medications: set[str] = set()
    for doc in documents:
        if not doc.parsed_data:
            continue
        diagnoses.update(diagnoses_from_parsed_data(doc.parsed_data))
        anamnesis.update(doc.parsed_data.get("anamnesis", []))
        operations.update(doc.parsed_data.get("operations", []))
        imaging_conclusions.update(doc.parsed_data.get("imaging_conclusions", []))
        medications.update(doc.parsed_data.get("medications", []))

    age = _calculate_age(patient.birth_date)
    dicom_bundle = _collect_dicom_bundle(db, patient_id, tenant_id)

    return {
        "patient_id": patient.id,
        "tenant_id": patient.tenant_id,
        "name": f"{patient.last_name} {patient.first_name}",
        "age": age,
        "gender": GENDER_LABELS.get(patient.gender, patient.gender),
        "diagnoses": sorted(diagnoses),
        "anamnesis": sorted(anamnesis),
        "operations": sorted(operations),
        "imaging_conclusions": sorted(imaging_conclusions),
        "medications": sorted(medications),
        "document_count": len(documents),
        "lab_results": _lab_results_from_documents(documents),
        "dicom": dicom_bundle,
    }


def _abnormal_lab_count(lab_results: dict) -> int:
    return sum(1 for item in lab_results.values() if isinstance(item, dict) and item.get("abnormal"))


def _clinical_imaging_risk_keywords(imaging_conclusions: list[str]) -> bool:
    text = " ".join(imaging_conclusions).casefold()
    return any(
        kw in text
        for kw in (
            "снижен овариальный резерв",
            "овариальн",
            "патолог",
            "образован",
            "кист",
            "миом",
            "воспал",
            "эндометрит",
            "гиперплаз",
            "полип",
        )
    )


def _rule_based_prediction(features: dict) -> dict:
    """Fallback when GPT/ProxyAPI is unavailable."""
    age = features.get("age", 50)
    diagnoses = features.get("diagnoses", [])
    anamnesis = features.get("anamnesis", [])
    operations = features.get("operations", [])
    imaging_conclusions = features.get("imaging_conclusions", [])
    medications = features.get("medications", [])
    lab_results = features.get("lab_results", {})
    dicom = features.get("dicom", {})
    findings = dicom.get("findings", [])
    condition_count = len(diagnoses) + len(anamnesis)
    abnormal_labs = _abnormal_lab_count(lab_results)

    readmission = min(95, 15 + condition_count * 8 + max(0, age - 60) // 2)
    complication = min(95, 10 + condition_count * 10 + len(medications) * 3)
    complication = min(95, complication + abnormal_labs * 2)
    if operations:
        complication = min(95, complication + 5)
    if _clinical_imaging_risk_keywords(imaging_conclusions):
        complication = min(95, complication + 8)
        readmission = min(95, readmission + 5)

    abnormal = any(
        w in " ".join(findings).lower()
        for w in ("mass", "fracture", "опухол", "перелом", "кровоизлиян", "malignan", "abnormal")
    )
    if abnormal:
        complication = min(95, complication + 15)
        readmission = min(95, readmission + 10)

    tumors = dicom.get("measurements", {}).get("tumors", [])
    if tumors:
        complication = min(95, complication + 10)

    factors = []
    if age >= 65:
        factors.append("Возраст старше 65 лет")
    if condition_count >= 3:
        factors.append(f"Множественные диагнозы ({condition_count})")
    if len(medications) >= 5:
        factors.append(f"Полипрагмазия ({len(medications)} препаратов)")
    if abnormal_labs:
        factors.append(f"Отклонения в лабораторных анализах ({abnormal_labs})")
    if operations:
        factors.append(f"Перенесённые операции ({len(operations)})")
    if imaging_conclusions:
        factors.append(f"Заключения визуализации: {', '.join(imaging_conclusions[:2])}")
    if findings:
        factors.append(f"Патологические находки на визуализации ({len(findings)})")
    if dicom.get("study_count", 0) > 0:
        factors.append(f"DICOM-исследований: {dicom['study_count']}")
    if not factors:
        factors.append("Недостаточно клинических данных для точной оценки")

    recommendations = [
        "Плановое наблюдение в течение 30 дней после выписки",
        "Контроль назначенной терапии и соблюдения режима",
        "Повторная консультация при ухудшении состояния",
    ]
    if abnormal:
        recommendations.insert(0, "Корреляция визуализационных находок с клинической картиной")

    return {
        "readmission_risk": readmission,
        "complication_risk": complication,
        "factors": factors,
        "recommendations": recommendations,
        "imaging_notes": findings[:3],
        "guideline_alignment": dicom.get("guideline_alignment", [])[:5],
        "source": "rule_based",
    }


async def _gpt_prediction(features: dict, *, use_dicom: bool = True) -> dict:
    dicom = features.get("dicom", {})
    has_dicom = use_dicom and dicom.get("study_count", 0) > 0

    if has_dicom:
        prompt = build_gpt_user_prompt(features, dicom)
        system = SYSTEM_PROMPT_DICOM
    else:
        prompt = build_gpt_clinical_prompt(features)
        system = (
            "Ты клинический аналитик. Учитывай лабораторные данные, операции и заключения УЗИ. "
            "Отвечай только валидным JSON на русском языке. Риски — целые числа от 0 до 100."
        )

    result = await chat_completion_json(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
    )
    result["source"] = "gpt_dicom" if has_dicom else "gpt"
    if has_dicom and "guideline_alignment" not in result:
        result["guideline_alignment"] = dicom.get("guideline_alignment", [])[:5]
    return result


def _save_prediction(
    db: Session,
    features: dict,
    prediction_data: dict,
    confidence: float,
    patient_id: int,
    user_id: int,
    analysis_id: int | None,
    tenant_id: int | None,
    *,
    prediction_type: str = "readmission",
) -> Prediction:
    readmission = float(prediction_data.get("readmission_risk", 0))
    complication = float(prediction_data.get("complication_risk", 0))

    prediction = Prediction(
        tenant_id=tenant_id or features.get("tenant_id", 1),
        patient_id=patient_id,
        user_id=user_id,
        analysis_id=analysis_id,
        type=prediction_type,
        features=features,
        prediction={
            "readmission_risk": readmission,
            "complication_risk": complication,
            "factors": prediction_data.get("factors", []),
            "recommendations": prediction_data.get("recommendations", []),
            "imaging_notes": prediction_data.get("imaging_notes", []),
            "guideline_alignment": prediction_data.get("guideline_alignment", []),
            "source": prediction_data.get("source", "unknown"),
            "dicom_sources": features.get("dicom", {}).get("sources", []),
        },
        probabilities={
            "readmission": readmission / 100.0,
            "complication": complication / 100.0,
        },
        confidence_score=confidence,
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(prediction)
    db.commit()
    db.refresh(prediction)
    return prediction


@trace_span("predictor_agent", {"agent": "predictor"})
def predict_risk(
    db: Session,
    patient_id: int,
    user_id: int,
    analysis_id: int | None = None,
    tenant_id: int | None = None,
) -> Prediction:
    import asyncio

    features = _collect_patient_features(db, patient_id, user_id, tenant_id)
    use_dicom = features.get("dicom", {}).get("study_count", 0) > 0

    try:
        prediction_data = asyncio.run(_gpt_prediction(features, use_dicom=use_dicom))
        confidence = 0.88 if use_dicom else 0.85
    except (OpenAIClientError, Exception) as exc:
        logger.warning("GPT prediction failed for patient %s: %s — using rule-based fallback", patient_id, exc)
        prediction_data = _rule_based_prediction(features)
        confidence = 0.58 if use_dicom else 0.55

    if settings.SHAP_ENABLED and settings.SHAP_SYNC_ON_PREDICT:
        from app.services.shap_explainer import attach_shap_to_prediction_dict

        prediction = _save_prediction(
            db, features, prediction_data, confidence, patient_id, user_id, analysis_id, tenant_id
        )
        prediction_data = attach_shap_to_prediction_dict(
            features, dict(prediction.prediction or {}), prediction_id=prediction.id
        )
        prediction.prediction = prediction_data
        db.commit()
        db.refresh(prediction)
    else:
        prediction = _save_prediction(
            db, features, prediction_data, confidence, patient_id, user_id, analysis_id, tenant_id
        )

    if settings.SHAP_ENABLED and not settings.SHAP_SYNC_ON_PREDICT:
        try:
            from app.tasks.celery_app import redis_available
            from app.tasks.shap_task import compute_shap_values_task
            from app.services.shap_explainer import attach_shap_to_prediction_dict

            if redis_available():
                compute_shap_values_task.delay(prediction.id)
            else:
                pred_data = attach_shap_to_prediction_dict(
                    features, dict(prediction.prediction or {}), prediction_id=prediction.id
                )
                prediction.prediction = pred_data
                db.commit()
                db.refresh(prediction)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async SHAP dispatch failed: %s", exc)

    return prediction


@trace_span("predictor_agent", {"agent": "predictor", "mode": "dicom"})
def predict_risk_with_dicom(
    db: Session,
    patient_id: int,
    user_id: int,
    analysis_id: int | None = None,
    tenant_id: int | None = None,
) -> Prediction:
    """Force DICOM-enriched prediction; processes unprocessed studies first."""
    import asyncio

    from app.services.dicom_text_extractor import DicomTextExtractor

    query = db.query(DicomStudy).filter(
        DicomStudy.patient_id == patient_id,
        DicomStudy.status == "ready",
    )
    if tenant_id is not None:
        query = query.filter(DicomStudy.tenant_id == tenant_id)
    studies = query.all()

    extractor = DicomTextExtractor(db)
    for study in studies:
        if not study.clinical_context:
            try:
                extractor.process_study(study.study_uid)
            except Exception as exc:  # noqa: BLE001
                logger.warning("DICOM context processing failed for %s: %s", study.study_uid, exc)

    features = _collect_patient_features(db, patient_id, user_id, tenant_id)

    try:
        prediction_data = asyncio.run(_gpt_prediction(features, use_dicom=True))
        confidence = 0.90
    except (OpenAIClientError, Exception) as exc:
        logger.warning("GPT DICOM prediction failed for patient %s: %s", patient_id, exc)
        prediction_data = _rule_based_prediction(features)
        confidence = 0.60

    if settings.SHAP_ENABLED and settings.SHAP_SYNC_ON_PREDICT:
        from app.services.shap_explainer import attach_shap_to_prediction_dict

        prediction = _save_prediction(
            db,
            features,
            prediction_data,
            confidence,
            patient_id,
            user_id,
            analysis_id,
            tenant_id,
            prediction_type="readmission_dicom",
        )
        prediction_data = attach_shap_to_prediction_dict(
            features, dict(prediction.prediction or {}), prediction_id=prediction.id
        )
        prediction.prediction = prediction_data
        db.commit()
        db.refresh(prediction)
    else:
        prediction = _save_prediction(
            db,
            features,
            prediction_data,
            confidence,
            patient_id,
            user_id,
            analysis_id,
            tenant_id,
            prediction_type="readmission_dicom",
        )

    if settings.SHAP_ENABLED and not settings.SHAP_SYNC_ON_PREDICT:
        try:
            from app.tasks.celery_app import redis_available
            from app.tasks.shap_task import compute_shap_values_task
            from app.services.shap_explainer import attach_shap_to_prediction_dict

            if redis_available():
                compute_shap_values_task.delay(prediction.id)
            else:
                pred_data = attach_shap_to_prediction_dict(
                    features, dict(prediction.prediction or {}), prediction_id=prediction.id
                )
                prediction.prediction = pred_data
                db.commit()
                db.refresh(prediction)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Async SHAP dispatch failed: %s", exc)

    return prediction
