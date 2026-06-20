import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import hash_password, require_admin, require_super_admin
from app.config import settings
from app.database import get_db
from app.models import AuditLog, Document, Patient, Prediction, Tenant, User
from app.services.access import ROLES, is_super_admin
from app.services.audit import log_audit
from app.services.encryption import rotate_encryption_key

router = APIRouter(prefix="/admin", tags=["admin"])


class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    subdomain: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    settings: dict | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    settings: dict | None = None
    is_active: bool | None = None


class TenantResponse(BaseModel):
    id: int
    name: str
    subdomain: str
    settings: dict | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="doctor")
    tenant_id: int | None = None


class UserAdminResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    tenant_id: int | None
    is_blocked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleUpdate(BaseModel):
    role: str


class AuditLogResponse(BaseModel):
    id: int
    user_id: int | None
    tenant_id: int | None
    action: str
    resource_type: str | None
    resource_id: int | None
    ip_address: str | None
    details: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    tenant_mode: bool
    encryption_enabled: bool
    tenants_count: int
    users_count: int
    patients_count: int
    documents_count: int


class RotateKeyRequest(BaseModel):
    new_key: str = Field(min_length=20)


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    data: TenantCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_super_admin)],
):
    if db.query(Tenant).filter(Tenant.subdomain == data.subdomain).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subdomain already exists")

    tenant = Tenant(
        name=data.name,
        subdomain=data.subdomain,
        settings=data.settings or {},
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    if is_super_admin(current_user):
        return db.query(Tenant).order_by(Tenant.name).all()
    if current_user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        return [tenant] if tenant else []
    return []


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if not is_super_admin(current_user) and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return tenant


@router.put("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if not is_super_admin(current_user) and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    db.commit()
    db.refresh(tenant)
    return tenant


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_super_admin)],
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    db.query(Prediction).filter(Prediction.tenant_id == tenant_id).delete()
    db.query(Document).filter(Document.tenant_id == tenant_id).delete()
    db.query(Patient).filter(Patient.tenant_id == tenant_id).delete()
    db.query(User).filter(User.tenant_id == tenant_id).delete()
    db.query(AuditLog).filter(AuditLog.tenant_id == tenant_id).delete()
    db.delete(tenant)
    db.commit()

    enc_dir = Path(settings.STORAGE_PATH) / "encrypted" / f"tenant_{tenant_id}"
    if enc_dir.exists():
        shutil.rmtree(enc_dir, ignore_errors=True)


@router.post("/users", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    if data.role not in ROLES or data.role == "super_admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    tenant_id = data.tenant_id
    if is_super_admin(current_user):
        if tenant_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id required")
    else:
        tenant_id = current_user.tenant_id

    existing = db.query(User).filter(User.tenant_id == tenant_id, User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = User(
        tenant_id=tenant_id,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserAdminResponse])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    tenant_id: int | None = Query(None),
):
    query = db.query(User)
    if is_super_admin(current_user):
        if tenant_id is not None:
            query = query.filter(User.tenant_id == tenant_id)
    else:
        query = query.filter(User.tenant_id == current_user.tenant_id)
    return query.order_by(User.created_at.desc()).all()


@router.put("/users/{user_id}/role", response_model=UserAdminResponse)
def update_user_role(
    user_id: int,
    data: RoleUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    if data.role not in ROLES or data.role == "super_admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not is_super_admin(current_user) and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    user.role = data.role
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/block", response_model=UserAdminResponse)
def block_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role == "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot block super admin")
    if not is_super_admin(current_user) and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    user.is_blocked = True
    db.commit()
    db.refresh(user)
    return user


@router.get("/audit", response_model=list[AuditLogResponse])
def list_audit(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    tenant_id: int | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    query = db.query(AuditLog)
    if is_super_admin(current_user):
        if tenant_id is not None:
            query = query.filter(AuditLog.tenant_id == tenant_id)
    else:
        query = query.filter(AuditLog.tenant_id == current_user.tenant_id)

    if action:
        query = query.filter(AuditLog.action == action)

    return query.order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/health", response_model=HealthResponse)
def admin_health(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    return HealthResponse(
        status="ok",
        tenant_mode=settings.TENANT_MODE,
        encryption_enabled=settings.ENCRYPTION_ENABLED,
        tenants_count=db.query(Tenant).count(),
        users_count=db.query(User).count(),
        patients_count=db.query(Patient).count(),
        documents_count=db.query(Document).count(),
    )


@router.post("/encryption/rotate")
def rotate_key(
    data: RotateKeyRequest,
    current_user: Annotated[User, Depends(require_super_admin)],
):
    count = rotate_encryption_key(data.new_key)
    return {"status": "rotated", "files_count": count}


# --- Phase 4: Self-healing RAG (admin only) --------------------------------


@router.get("/self-healing/stats")
def self_healing_stats(current_user: Annotated[User, Depends(require_admin)]):
    from app.services.self_healing.vector_store import get_knowledge_base

    kb = get_knowledge_base()
    if kb is None:
        return {"enabled": False, "total_fixes": 0}
    stats = kb.get_stats()
    stats["enabled"] = True
    return stats


@router.get("/self-healing/fixes")
def self_healing_list(current_user: Annotated[User, Depends(require_admin)]):
    from app.services.self_healing.vector_store import get_knowledge_base

    kb = get_knowledge_base()
    return kb.list_all() if kb else []


@router.post("/self-healing/seed-fixes")
def self_healing_seed(
    current_user: Annotated[User, Depends(require_super_admin)],
    overwrite: bool = Query(False),
):
    from app.services.self_healing.vector_store import seed_knowledge_base

    imported, skipped = seed_knowledge_base(overwrite=overwrite)
    return {"imported": imported, "skipped": skipped}


@router.post("/self-healing/confirm/{fix_id}")
def self_healing_confirm(
    fix_id: int,
    current_user: Annotated[User, Depends(require_super_admin)],
):
    from app.services.self_healing.vector_store import get_knowledge_base

    kb = get_knowledge_base()
    if kb is None or not kb.confirm_fix(fix_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fix not found")
    return {"status": "confirmed", "fix_id": fix_id}


@router.delete("/self-healing/fixes/{fix_id}", status_code=status.HTTP_204_NO_CONTENT)
def self_healing_delete(
    fix_id: int,
    current_user: Annotated[User, Depends(require_super_admin)],
):
    from app.services.self_healing.vector_store import get_knowledge_base

    kb = get_knowledge_base()
    if kb is None or not kb.delete_fix(fix_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fix not found")
