from fastapi import HTTPException, status
from sqlalchemy.orm import Query, Session

from app.models import Document, Patient, User

ROLES = frozenset({"super_admin", "admin", "doctor", "researcher", "viewer"})
WRITE_ROLES = frozenset({"super_admin", "admin", "doctor"})
ADMIN_ROLES = frozenset({"super_admin", "admin"})


def is_super_admin(user: User) -> bool:
    return user.role == "super_admin"


def is_admin(user: User) -> bool:
    return user.role in ADMIN_ROLES


def effective_tenant_id(user: User, request_tenant_id: int | None = None) -> int | None:
    if is_super_admin(user) and request_tenant_id is not None:
        return request_tenant_id
    return user.tenant_id


def require_role(user: User, *allowed: str) -> None:
    if is_super_admin(user):
        return
    if user.role not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{user.role}' not allowed. Required: {', '.join(allowed)}",
        )


def require_tenant_access(user: User, tenant_id: int) -> None:
    if is_super_admin(user):
        return
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")


def patients_query(db: Session, user: User, tenant_id: int | None = None) -> Query:
    query = db.query(Patient)
    tid = effective_tenant_id(user, tenant_id)
    if tid is not None:
        query = query.filter(Patient.tenant_id == tid)
    if user.role == "doctor":
        pass  # doctors see all patients in tenant (read); write filtered separately
    return query


def can_view_patient(user: User, patient: Patient) -> bool:
    if is_super_admin(user):
        return True
    if user.tenant_id != patient.tenant_id:
        return False
    return True


def can_modify_patient(user: User, patient: Patient) -> bool:
    if user.role == "viewer":
        return False
    if user.role == "researcher":
        return False
    if is_super_admin(user) or user.role == "admin":
        return True
    if user.role == "doctor":
        return patient.user_id == user.id
    return False


def can_create_patient(user: User) -> bool:
    return user.role in WRITE_ROLES


def can_delete_patient(user: User) -> bool:
    return user.role in ADMIN_ROLES or is_super_admin(user)


def can_upload_document(user: User) -> bool:
    return user.role in WRITE_ROLES


def can_predict(user: User) -> bool:
    return user.role in WRITE_ROLES


def can_export(user: User) -> bool:
    return user.role in WRITE_ROLES | {"viewer"}


def anonymize_patient(patient: Patient) -> dict:
    return {
        "id": patient.id,
        "first_name": f"P-{patient.id}",
        "last_name": "ANON",
        "middle_name": None,
        "birth_date": patient.birth_date.isoformat()[:4] + "-01-01",
        "gender": patient.gender,
        "phone": "***",
        "email": None,
        "created_at": patient.created_at.isoformat(),
        "updated_at": patient.updated_at.isoformat(),
    }
