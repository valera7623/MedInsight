import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Document, Patient, User
from app.services.extractor import extract_entities
from app.services.parser import SUPPORTED_EXTENSIONS, parse_document

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",
}


class DocumentResponse(BaseModel):
    id: int
    patient_id: int
    user_id: int
    filename: str
    file_path: str
    file_size: int
    mime_type: str
    document_type: str
    parsed_data: dict | None
    status: str
    created_at: datetime
    parsed_at: datetime | None

    model_config = {"from_attributes": True}


def _get_document_or_404(db: Session, doc_id: int, user_id: int) -> Document:
    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.user_id == user_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


def _process_document(doc: Document, db: Session) -> None:
    try:
        text = parse_document(doc.file_path)
        parsed = extract_entities(text)
        doc.parsed_data = parsed
        doc.status = "parsed"
        doc.parsed_at = datetime.utcnow()
    except Exception as exc:
        logger.exception("Failed to parse document %s: %s", doc.id, exc)
        doc.status = "failed"
        doc.parsed_data = {"error": str(exc), "full_text": ""}
    db.commit()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    patient_id: int = Form(...),
    document_type: str = Form("discharge"),
    file: UploadFile = File(...),
):
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id, Patient.user_id == current_user.id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only DOCX and PDF files are supported",
        )

    if file.content_type and file.content_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type: {file.content_type}",
        )

    storage_dir = Path(settings.STORAGE_PATH) / str(current_user.id) / str(patient_id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    dest_path = storage_dir / safe_name

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    doc = Document(
        patient_id=patient_id,
        user_id=current_user.id,
        filename=safe_name,
        file_path=str(dest_path),
        file_size=len(content),
        mime_type=file.content_type or "application/octet-stream",
        document_type=document_type,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _process_document(doc, db)
    db.refresh(doc)
    return doc


@router.get("/patient/{patient_id}", response_model=list[DocumentResponse])
def list_patient_documents(
    patient_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    patient = (
        db.query(Patient)
        .filter(Patient.id == patient_id, Patient.user_id == current_user.id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    return (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return _get_document_or_404(db, document_id, current_user.id)
