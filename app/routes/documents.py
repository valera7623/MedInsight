import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.middleware.tenant import get_request_tenant_id
from app.models import AnalysisJob, Document, Patient, User
from app.services.access import can_upload_document, can_view_patient, effective_tenant_id, is_super_admin
from app.services.audit import log_audit
from app.services.list_queries import DOCUMENT_SEARCH_FIELDS, DOCUMENT_SORT, documents_scope
from app.utils.pagination import PaginationParams, paginate
from app.services.encryption import EncryptionError, decrypt_file, encrypt_bytes, ensure_encryption_key
from app.services.extractor import extract_entities
from app.services.parser import SUPPORTED_EXTENSIONS, SUPPORTED_MIMES, parse_document, parse_document_from_bytes
from app.tasks.celery_app import redis_available
from app.tasks.parse_task import parse_document_task

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)

ALLOWED_MIMES = SUPPORTED_MIMES | {
    "application/octet-stream",
}


class DocumentResponse(BaseModel):
    id: int
    tenant_id: int
    patient_id: int
    user_id: int
    filename: str
    file_size: int
    mime_type: str
    document_type: str
    is_encrypted: bool
    parsed_data: dict | None
    status: str
    created_at: datetime
    parsed_at: datetime | None

    model_config = {"from_attributes": True}


def _get_document_or_404(
    db: Session, doc_id: int, user: User, request: Request | None = None
) -> Document:
    tid = effective_tenant_id(user, get_request_tenant_id(request) if request else None)
    query = db.query(Document).filter(Document.id == doc_id)
    if tid is not None:
        query = query.filter(Document.tenant_id == tid)
    doc = query.first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    # Department-level access: the user must be allowed to see the patient.
    if doc.patient is not None and not can_view_patient(user, doc.patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


def _parse_document_content(doc: Document) -> str:
    if doc.is_encrypted or doc.file_path.endswith(".age"):
        content = decrypt_file(doc.file_path)
        return parse_document_from_bytes(content, doc.filename)
    return parse_document(doc.file_path)


def _process_document_sync(doc: Document, db: Session) -> None:
    try:
        text = _parse_document_content(doc)
        parsed = extract_entities(text)
        doc.parsed_data = parsed
        doc.status = "parsed"
        doc.parsed_at = datetime.utcnow()
    except Exception as exc:
        logger.exception("Failed to parse document %s: %s", doc.id, exc)
        doc.status = "failed"
        doc.parsed_data = {"error": str(exc), "full_text": ""}
    db.commit()


def _enqueue_parse(doc: Document, db: Session, user_id: int) -> str | None:
    if not redis_available():
        logger.info("Redis unavailable — sync parse for document %s", doc.id)
        _process_document_sync(doc, db)
        return None

    try:
        job = AnalysisJob(
            tenant_id=doc.tenant_id,
            patient_id=doc.patient_id,
            user_id=user_id,
            document_id=doc.id,
            type="parse",
            status="pending",
        )
        db.add(job)
        doc.status = "processing"
        db.commit()
        db.refresh(job)

        task = parse_document_task.delay(job.id, doc.id)
        job.celery_task_id = task.id
        db.commit()
        return str(job.id)
    except Exception as exc:
        logger.warning("Celery unavailable, falling back to sync parse: %s", exc)
        db.rollback()
        _process_document_sync(doc, db)
        return None


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    patient_id: int = Form(...),
    document_type: str = Form("discharge"),
    file: UploadFile = File(...),
):
    if not can_upload_document(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot upload documents")

    header_tid = get_request_tenant_id(request)
    patient_query = db.query(Patient).filter(Patient.id == patient_id)

    if is_super_admin(current_user):
        if header_tid is not None:
            patient_query = patient_query.filter(Patient.tenant_id == header_tid)
    elif current_user.tenant_id is not None:
        patient_query = patient_query.filter(Patient.tenant_id == current_user.tenant_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to a tenant. Re-login or contact admin.",
        )

    patient = patient_query.first()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    if not can_view_patient(current_user, patient):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patient outside your scope")

    tenant_id = patient.tenant_id

    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Поддерживаются файлы: {supported}",
        )

    if file.content_type and file.content_type not in ALLOWED_MIMES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported MIME type: {file.content_type}")

    safe_name = Path(file.filename).name
    content = await file.read()

    try:
        ensure_encryption_key()
        file_path, stored_size = encrypt_bytes(content, tenant_id, patient_id, safe_name)
    except EncryptionError as exc:
        logger.error("Encryption failed during upload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File encryption unavailable. Check ENCRYPTION_KEY or secrets volume.",
        ) from exc

    doc = Document(
        tenant_id=tenant_id,
        patient_id=patient_id,
        user_id=current_user.id,
        filename=safe_name,
        file_path=file_path,
        file_size=stored_size,
        mime_type=file.content_type or "application/octet-stream",
        document_type=document_type,
        is_encrypted=settings.ENCRYPTION_ENABLED,
        status="uploaded",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=tenant_id,
        action="upload",
        resource_type="document",
        resource_id=doc.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"filename": safe_name, "encrypted": doc.is_encrypted},
    )

    _enqueue_parse(doc, db, current_user.id)
    db.refresh(doc)
    return doc


@router.get("")
def list_documents(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    patient_id: int | None = Query(None),
    document_type: str | None = Query(None),
    doc_status: str | None = Query(None, alias="status"),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    tid = effective_tenant_id(current_user, get_request_tenant_id(request))
    query = documents_scope(db, current_user, tid)
    params = PaginationParams(
        page=page,
        limit=limit,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        filters={"patient_id": patient_id, "document_type": document_type, "status": doc_status},
    )
    return paginate(
        query,
        params,
        model=Document,
        search_fields=DOCUMENT_SEARCH_FIELDS,
        allowed_sort=DOCUMENT_SORT,
        serializer=lambda d: DocumentResponse.model_validate(d).model_dump(),
    )


@router.get("/patient/{patient_id}", response_model=list[DocumentResponse])
def list_patient_documents(
    patient_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    tenant_id = effective_tenant_id(current_user, get_request_tenant_id(request))
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient or not can_view_patient(current_user, patient):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    return (
        db.query(Document)
        .filter(Document.patient_id == patient_id, Document.tenant_id == patient.tenant_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    return _get_document_or_404(db, document_id, current_user, request)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    inline: bool = Query(False, description="Open in browser when supported (PDF)"),
):
    doc = _get_document_or_404(db, document_id, current_user, request)

    if doc.is_encrypted or doc.file_path.endswith(".age"):
        content = decrypt_file(doc.file_path)
    else:
        content = Path(doc.file_path).read_bytes()

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=doc.tenant_id,
        action="download",
        resource_type="document",
        resource_id=doc.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    disposition = "inline" if inline else "attachment"
    return Response(
        content=content,
        media_type=doc.mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{doc.filename}"'},
    )
