import logging

from sqlalchemy.orm import Session

from app.models import Patient, Prediction
from app.services.openai_client import OpenAIClientError, chat_completion_json
from app.services.predictor import _collect_patient_features, _rule_based_prediction
from app.utils.tracing import trace_span

logger = logging.getLogger(__name__)


def _rule_based_insights(features: dict, predictions: list[dict]) -> dict:
    latest = predictions[0] if predictions else _rule_based_prediction(features)
    pred = latest.get("prediction", latest) if isinstance(latest, dict) else {}

    readmission = pred.get("readmission_risk", 30)
    complication = pred.get("complication_risk", 25)

    summary = (
        f"Пациент {features.get('name', '')}, {features.get('age')} лет. "
        f"Диагнозы: {', '.join(features.get('diagnoses', [])[:5]) or 'не указаны'}. "
        f"Риск реадмиссии: {readmission}%, риск осложнений: {complication}%."
    )
    recommendations = pred.get("recommendations", [
        "Плановое наблюдение",
        "Контроль назначенной терапии",
    ])
    return {"summary": summary, "recommendations": recommendations, "source": "rule_based"}


async def _gpt_insights(features: dict, predictions: list[dict]) -> dict:
    pred_summary = []
    for p in predictions[:3]:
        pred_data = p.get("prediction", p)
        pred_summary.append(
            f"реадмиссия {pred_data.get('readmission_risk', '?')}%, "
            f"осложнения {pred_data.get('complication_risk', '?')}%"
        )

    prompt = f"""Создай краткую клиническую заметку по пациенту:
- Имя: {features.get('name')}
- Диагнозы: {features.get('diagnoses', [])}
- Лекарства: {features.get('medications', [])}
- Прогнозы: {pred_summary or 'нет данных'}

Верни JSON: {{"summary": "...", "recommendations": ["..."]}}"""

    result = await chat_completion_json(
        messages=[
            {
                "role": "system",
                "content": "Ты клинический ассистент. Отвечай только валидным JSON на русском языке.",
            },
            {"role": "user", "content": prompt},
        ]
    )
    result["source"] = "gpt"
    return result


@trace_span("summarizer_agent", {"agent": "summarizer"})
def generate_insights(db: Session, patient_id: int, user_id: int) -> dict:
    import asyncio

    features = _collect_patient_features(db, patient_id, user_id)

    predictions = (
        db.query(Prediction)
        .filter(Prediction.patient_id == patient_id, Prediction.user_id == user_id)
        .order_by(Prediction.created_at.desc())
        .limit(5)
        .all()
    )
    pred_dicts = [
        {
            "prediction": p.prediction,
            "created_at": p.created_at.isoformat(),
        }
        for p in predictions
    ]

    try:
        return asyncio.run(_gpt_insights(features, pred_dicts))
    except (OpenAIClientError, Exception) as exc:
        logger.warning("GPT insights failed for patient %s: %s — using rule-based fallback", patient_id, exc)
        return _rule_based_insights(features, pred_dicts)
