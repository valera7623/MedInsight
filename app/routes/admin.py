from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password, require_admin, require_super_admin
from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import rate_limit
from app.models import (
    AnalysisJob,
    AuditLog,
    Department,
    DicomStudy,
    Document,
    Patient,
    Payment,
    Prediction,
    Subscription,
    TelegramUser,
    Tenant,
    User,
    UserPreference,
)
from app.middleware.tenant import get_request_tenant_id
from app.services.access import ROLES, is_super_admin
from app.services.audit import log_audit
from app.services.tenant_deletion import delete_tenant_with_dependencies
from app.services.encryption import rotate_encryption_key
from app.services.list_queries import (
    AUDIT_SORT,
    DEPARTMENT_SEARCH_FIELDS,
    DEPARTMENT_SORT,
    USER_SEARCH_FIELDS,
    USER_SORT,
    audit_scope,
    departments_scope,
    users_scope,
)
from app.utils.pagination import PaginationParams, paginate

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
    department_id: int | None = None
    can_see_all_patients: bool = False


class UserAdminResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    tenant_id: int | None
    department_id: int | None
    can_see_all_patients: bool
    is_blocked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    head_doctor_id: int | None = None
    tenant_id: int | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    head_doctor_id: int | None = None


class DepartmentResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    head_doctor_id: int | None
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
@rate_limit(
    limit=settings.RATE_LIMIT_ADMIN_PER_MINUTE,
    period=60,
    name="admin_create_tenant",
)
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

    from app.services.cache_invalidation import invalidate_tenant_cache

    invalidate_tenant_cache(db, tenant.id)
    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=tenant.id,
        action="tenant_created",
        resource_type="tenant",
        resource_id=tenant.id,
        details={"name": tenant.name, "subdomain": tenant.subdomain},
    )
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

    from app.services.cache_invalidation import invalidate_tenant_cache

    invalidate_tenant_cache(db, tenant.id)
    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=tenant.id,
        action="tenant_updated",
        resource_type="tenant",
        resource_id=tenant.id,
        details=data.model_dump(exclude_unset=True),
    )
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
    if tenant.subdomain == settings.DEFAULT_TENANT_SUBDOMAIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default clinic",
        )

    tenant_name = tenant.name
    tenant_subdomain = tenant.subdomain
    try:
        delete_tenant_with_dependencies(db, tenant)
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to delete tenant %s: %s", tenant_id, exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Не удалось удалить клинику: есть связанные записи или ограничение базы данных.",
        ) from exc

    from app.services.cache_invalidation import invalidate_tenant_cache

    invalidate_tenant_cache(db, tenant_id)
    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=None,
        action="tenant_deleted",
        resource_type="tenant",
        resource_id=tenant_id,
        details={"name": tenant_name, "subdomain": tenant_subdomain},
    )


@router.post("/users", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(
    limit=settings.RATE_LIMIT_ADMIN_PER_MINUTE,
    period=60,
    name="admin_create_user",
)
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

    if data.department_id is not None:
        dept = db.query(Department).filter(Department.id == data.department_id).first()
        if not dept or (tenant_id is not None and dept.tenant_id != tenant_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department for tenant")

    user = User(
        tenant_id=tenant_id,
        department_id=data.department_id,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        can_see_all_patients=data.can_see_all_patients,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _user_dump(u: User) -> dict:
    return UserAdminResponse.model_validate(u).model_dump(mode="json")


@router.get("/users")
def list_users(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    tenant_id: int | None = Query(None),
    page: int | None = Query(None, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    query = users_scope(db, current_user, tenant_id)
    if is_active is not None:
        query = query.filter(User.is_blocked.is_(not is_active))

    # Back-compat: no pagination/filter params -> plain array (legacy admin UI).
    if page is None and search is None and role is None and is_active is None:
        return [_user_dump(u) for u in query.order_by(User.created_at.desc()).all()]

    params = PaginationParams(
        page=page or 1, limit=limit, search=search, sort_by=sort_by, sort_order=sort_order,
        filters={"role": role},
    )
    return paginate(
        query, params, model=User, search_fields=USER_SEARCH_FIELDS,
        allowed_sort=USER_SORT, serializer=_user_dump,
    )


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


@router.post("/users/{user_id}/unblock", response_model=UserAdminResponse)
def unblock_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not is_super_admin(current_user) and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    user.is_blocked = False
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role == "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete super admin")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
    if not is_super_admin(current_user) and user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    new_owner_id = current_user.id

    # Reassign NOT NULL user_id references to the acting admin.
    for model in (Patient, Document, Prediction, AnalysisJob, DicomStudy):
        db.query(model).filter(model.user_id == user_id).update(
            {model.user_id: new_owner_id}, synchronize_session=False
        )

    # Clear nullable user references.
    db.query(Patient).filter(Patient.attending_doctor_id == user_id).update(
        {Patient.attending_doctor_id: None}, synchronize_session=False
    )
    db.query(Department).filter(Department.head_doctor_id == user_id).update(
        {Department.head_doctor_id: None}, synchronize_session=False
    )
    db.query(AuditLog).filter(AuditLog.user_id == user_id).update(
        {AuditLog.user_id: None}, synchronize_session=False
    )
    db.query(Subscription).filter(Subscription.user_id == user_id).update(
        {Subscription.user_id: None}, synchronize_session=False
    )
    db.query(Payment).filter(Payment.user_id == user_id).update(
        {Payment.user_id: None}, synchronize_session=False
    )

    # Remove rows that block user deletion.
    db.query(TelegramUser).filter(TelegramUser.user_id == user_id).delete(synchronize_session=False)
    db.query(UserPreference).filter(UserPreference.user_id == user_id).delete(synchronize_session=False)

    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="delete",
        resource_type="user",
        resource_id=user_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"deleted_email": user.email, "reassigned_to": new_owner_id},
    )

    db.delete(user)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete user: {exc}",
        ) from exc


def _resolve_admin_tenant(
    current_user: User,
    requested_tenant_id: int | None,
    db: Session,
    request: Request | None = None,
) -> int:
    if is_super_admin(current_user):
        tid = requested_tenant_id
        if tid is None and request is not None:
            tid = get_request_tenant_id(request)
        if tid is None:
            default = (
                db.query(Tenant)
                .filter(Tenant.subdomain == settings.DEFAULT_TENANT_SUBDOMAIN, Tenant.is_active.is_(True))
                .first()
            )
            if default is None:
                default = db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.id).first()
            if default is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No tenant available")
            tid = default.id
        return tid
    if current_user.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No tenant")
    return current_user.tenant_id


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    data: DepartmentCreate,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    tenant_id = _resolve_admin_tenant(current_user, data.tenant_id, db, request)
    dept = Department(tenant_id=tenant_id, name=data.name, head_doctor_id=data.head_doctor_id)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def _dept_dump(d: Department) -> dict:
    return DepartmentResponse.model_validate(d).model_dump(mode="json")


@router.get("/departments")
def list_departments(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    tenant_id: int | None = Query(None),
    page: int | None = Query(None, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    sort_by: str = Query("name"),
    sort_order: str = Query("asc"),
):
    query = departments_scope(db, current_user, tenant_id)

    # Back-compat: no pagination/search -> plain array (used by dropdowns).
    if page is None and search is None:
        return [_dept_dump(d) for d in query.order_by(Department.name).all()]

    params = PaginationParams(
        page=page or 1, limit=limit, search=search, sort_by=sort_by, sort_order=sort_order,
    )
    return paginate(
        query, params, model=Department, search_fields=DEPARTMENT_SEARCH_FIELDS,
        allowed_sort=DEPARTMENT_SORT, serializer=_dept_dump,
    )


def _get_department_owned(db: Session, dept_id: int, current_user: User) -> Department:
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    if not is_super_admin(current_user) and dept.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return dept


@router.put("/departments/{dept_id}", response_model=DepartmentResponse)
def update_department(
    dept_id: int,
    data: DepartmentUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    dept = _get_department_owned(db, dept_id, current_user)
    if data.name is not None:
        dept.name = data.name
    if data.head_doctor_id is not None:
        dept.head_doctor_id = data.head_doctor_id
    db.commit()
    db.refresh(dept)
    return dept


@router.delete("/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(
    dept_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    dept = _get_department_owned(db, dept_id, current_user)
    # Detach references so we don't orphan rows.
    db.query(Patient).filter(Patient.department_id == dept_id).update(
        {Patient.department_id: None}, synchronize_session=False
    )
    db.query(User).filter(User.department_id == dept_id).update(
        {User.department_id: None}, synchronize_session=False
    )
    db.delete(dept)
    db.commit()


def _audit_dump(a: AuditLog) -> dict:
    return AuditLogResponse.model_validate(a).model_dump(mode="json")


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


@router.get("/audit")
def list_audit(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    tenant_id: int | None = Query(None),
    action: str | None = Query(None),
    user_id: int | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    page: int | None = Query(None, ge=1),
    limit: int = Query(100, ge=1, le=500),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    query = audit_scope(db, current_user, tenant_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    dt_from = _parse_date(from_date)
    dt_to = _parse_date(to_date)
    if dt_from:
        query = query.filter(AuditLog.created_at >= dt_from)
    if dt_to:
        query = query.filter(AuditLog.created_at <= dt_to)

    # Back-compat: no pagination params -> plain array capped by limit (legacy UI).
    if page is None:
        rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
        return [_audit_dump(a) for a in rows]

    params = PaginationParams(
        page=page, limit=min(limit, 100), sort_by=sort_by, sort_order=sort_order,
    )
    return paginate(query, params, model=AuditLog, allowed_sort=AUDIT_SORT, serializer=_audit_dump)


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
