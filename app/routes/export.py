import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import Document, Patient, User
from app.services.access import can_export, effective_tenant_id

router = APIRouter(prefix="/export", tags=["export"])


def _format_full_name(patient: Patient) -> str:
    parts = [patient.last_name, patient.first_name]
    if patient.middle_name:
        parts.append(patient.middle_name)
    return " ".join(parts)


def _register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
        return "DejaVu", "DejaVu-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


@router.post("/patient/{patient_id}")
def export_patient_pdf(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    if not can_export(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot export")

    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id, Patient.tenant_id == tenant_id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    documents = (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.tenant_id == tenant_id)
        .order_by(Document.created_at.desc())
        .all()
    )

    all_diagnoses: set[str] = set()
    all_medications: set[str] = set()
    full_texts: list[str] = []

    for doc in documents:
        if doc.parsed_data:
            all_diagnoses.update(doc.parsed_data.get("diagnoses", []))
            all_medications.update(doc.parsed_data.get("medications", []))
            text = doc.parsed_data.get("full_text", "")
            if text:
                full_texts.append(f"[{doc.filename}]\n{text}")

    font_name, font_bold = _register_fonts()
    buffer = io.BytesIO()
    doc_pdf = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2 * cm, leftMargin=2 * cm,
                                topMargin=2 * cm, bottomMargin=2 * cm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontName=font_bold, fontSize=16)
    heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], fontName=font_bold, fontSize=12)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontName=font_name, fontSize=10, leading=14)

    gender_map = {"M": "Мужской", "F": "Женский", "O": "Другой"}
    elements = [
        Paragraph("MedInsight — Отчёт по пациенту", title_style),
        Spacer(1, 0.5 * cm),
    ]

    info_data = [
        ["Поле", "Значение"],
        ["ФИО", _format_full_name(patient)],
        ["Дата рождения", patient.birth_date.isoformat()],
        ["Пол", gender_map.get(patient.gender, patient.gender)],
        ["Телефон", patient.phone],
        ["Email", patient.email or "—"],
        ["Дата отчёта", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
    ]
    info_table = Table(info_data, colWidths=[5 * cm, 12 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5 * cm))

    elements.append(Paragraph("Диагнозы", heading_style))
    if all_diagnoses:
        for d in sorted(all_diagnoses):
            elements.append(Paragraph(f"• {d}", body_style))
    else:
        elements.append(Paragraph("Диагнозы не найдены", body_style))
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("Лекарства", heading_style))
    if all_medications:
        for m in sorted(all_medications, key=str.lower):
            elements.append(Paragraph(f"• {m}", body_style))
    else:
        elements.append(Paragraph("Лекарства не найдены", body_style))
    elements.append(Spacer(1, 0.3 * cm))

    elements.append(Paragraph("Текст выписки", heading_style))
    if full_texts:
        combined = "\n\n".join(full_texts)
        if len(combined) > 8000:
            combined = combined[:8000] + "..."
        for line in combined.split("\n"):
            if line.strip():
                elements.append(Paragraph(line.replace("&", "&amp;").replace("<", "&lt;"), body_style))
    else:
        elements.append(Paragraph("Текст документов отсутствует", body_style))

    doc_pdf.build(elements)
    buffer.seek(0)

    filename = f"patient_{patient_id}_report.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
