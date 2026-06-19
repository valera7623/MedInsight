import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Document, Patient, Prediction
from app.services.openai_client import OpenAIClientError, chat_completion_json

logger = logging.getLogger(__name__)

GENDER_LABELS = {"M": "мужской", "F": "женский", "O": "другой"}


def _calculate_age(birth_date: date) -> int:
    today = date.today()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _collect_patient_features(db: Session, patient_id: int, user_id: int, tenant_id: int | None = None) -> dict:
    query = db.query(Patient).filter(Patient.id == patient_id, Patient.user_id == user_id)
    if tenant_id is not None:
        query = query.filter(Patient.tenant_id == tenant_id)
    patient = query.first()
    if not patient:
        raise ValueError("Patient not found")

    documents = (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.user_id == user_id)
        .all()
    )

    diagnoses: set[str] = set()
    medications: set[str] = set()
    for doc in documents:
        if not doc.parsed_data:
            continue
        diagnoses.update(doc.parsed_data.get("diagnoses", []))
        medications.update(doc.parsed_data.get("medications", []))

    age = _calculate_age(patient.birth_date)
    return {
        "patient_id": patient.id,
        "tenant_id": patient.tenant_id,
        "name": f"{patient.last_name} {patient.first_name}",
        "age": age,
        "gender": GENDER_LABELS.get(patient.gender, patient.gender),
        "diagnoses": sorted(diagnoses),
        "medications": sorted(medications),
        "document_count": len(documents),
    }


def _rule_based_prediction(features: dict) -> dict:
    """Fallback when GPT/ProxyAPI is unavailable."""
    age = features.get("age", 50)
    diagnoses = features.get("diagnoses", [])
    medications = features.get("medications", [])

    readmission = min(95, 15 + len(diagnoses) * 8 + max(0, age - 60) // 2)
    complication = min(95, 10 + len(diagnoses) * 10 + len(medications) * 3)

    factors = []
    if age >= 65:
        factors.append("Возраст старше 65 лет")
    if len(diagnoses) >= 3:
        factors.append(f"Множественные диагнозы ({len(diagnoses)})")
    if len(medications) >= 5:
        factors.append(f"Полипрагмазия ({len(medications)} препаратов)")
    if not factors:
        factors.append("Недостаточно клинических данных для точной оценки")

    return {
        "readmission_risk": readmission,
        "complication_risk": complication,
        "factors": factors,
        "recommendations": [
            "Плановое наблюдение в течение 30 дней после выписки",
            "Контроль назначенной терапии и соблюдения режима",
            "Повторная консультация при ухудшении состояния",
        ],
        "source": "rule_based",
    }


async def _gpt_prediction(features: dict) -> dict:
    prompt = f"""Проанализируй данные пациента и оцени риск:
- Диагнозы: {features.get('diagnoses', [])}
- Лекарства: {features.get('medications', [])}
- Возраст: {features.get('age')}
- Пол: {features.get('gender')}

Оцени риск реадмиссии (0-100%), риск осложнений (0-100%).
Верни JSON: {{"readmission_risk": 42, "complication_risk": 35, "factors": ["..."], "recommendations": ["..."]}}"""

    result = await chat_completion_json(
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты клинический аналитик. Отвечай только валидным JSON на русском языке. "
                    "Риски — целые числа от 0 до 100."
                ),
            },
            {"role": "user", "content": prompt},
        ]
    )
    result["source"] = "gpt"
    return result


def predict_risk(
    db: Session,
    patient_id: int,
    user_id: int,
    analysis_id: int | None = None,
    tenant_id: int | None = None,
) -> Prediction:
    import asyncio

    features = _collect_patient_features(db, patient_id, user_id, tenant_id)

    try:
        prediction_data = asyncio.run(_gpt_prediction(features))
        confidence = 0.85
    except (OpenAIClientError, Exception) as exc:
        logger.warning("GPT prediction failed for patient %s: %s — using rule-based fallback", patient_id, exc)
        prediction_data = _rule_based_prediction(features)
        confidence = 0.55

    readmission = float(prediction_data.get("readmission_risk", 0))
    complication = float(prediction_data.get("complication_risk", 0))

    prediction = Prediction(
        tenant_id=tenant_id or features.get("tenant_id", 1),
        patient_id=patient_id,
        user_id=user_id,
        analysis_id=analysis_id,
        type="readmission",
        features=features,
        prediction={
            "readmission_risk": readmission,
            "complication_risk": complication,
            "factors": prediction_data.get("factors", []),
            "recommendations": prediction_data.get("recommendations", []),
            "source": prediction_data.get("source", "unknown"),
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
