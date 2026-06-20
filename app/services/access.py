from fastapi import HTTPException, status
from sqlalchemy import false, or_
from sqlalchemy.orm import Query, Session

from app.models import Document, Patient, User

ROLES = frozenset(
    {"super_admin", "admin", "head_of_department", "doctor", "nurse", "researcher", "viewer"}
)
# Roles allowed to create/modify patients, upload documents, run predictions.
WRITE_ROLES = frozenset({"super_admin", "admin", "head_of_department", "doctor"})
ADMIN_ROLES = frozenset({"super_admin", "admin"})
# Roles whose visibility is limited to their own department.
DEPARTMENT_SCOPED_ROLES = frozenset({"head_of_department", "doctor", "nurse"})
# Roles that may read across the whole tenant.
TENANT_WIDE_ROLES = frozenset({"admin", "researcher", "viewer"})


def is_super_admin(user: User) -> bool:
    return user.role == "super_admin"


def is_admin(user: User) -> bool:
    return user.role in ADMIN_ROLES


def sees_whole_tenant(user: User) -> bool:
    """True when the user may read every patient in their tenant."""
    return (
        is_super_admin(user)
        or user.role in TENANT_WIDE_ROLES
        or bool(getattr(user, "can_see_all_patients", False))
    )


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
    """Return a Patient query scoped to what the user is allowed to read."""
    query = db.query(Patient)
    tid = effective_tenant_id(user, tenant_id)
    if tid is not None:
        query = query.filter(Patient.tenant_id == tid)

    if sees_whole_tenant(user):
        return query

    if user.role in ("head_of_department", "nurse"):
        if user.department_id is None:
            return query.filter(false())
        return query.filter(Patient.department_id == user.department_id)

    if user.role == "doctor":
        conditions = [Patient.attending_doctor_id == user.id, Patient.user_id == user.id]
        if user.department_id is not None:
            conditions.append(Patient.department_id == user.department_id)
        return query.filter(or_(*conditions))

    return query.filter(false())


def can_view_patient(user: User, patient: Patient) -> bool:
    if is_super_admin(user):
        return True
    if user.tenant_id != patient.tenant_id:
        return False
    if sees_whole_tenant(user):
        return True
    if user.role in ("head_of_department", "nurse"):
        return user.department_id is not None and patient.department_id == user.department_id
    if user.role == "doctor":
        return (
            patient.attending_doctor_id == user.id
            or patient.user_id == user.id
            or (user.department_id is not None and patient.department_id == user.department_id)
        )
    return False


def can_modify_patient(user: User, patient: Patient) -> bool:
    if user.role in ("viewer", "researcher", "nurse"):
        return False
    if is_super_admin(user) or user.role == "admin":
        return user.tenant_id == patient.tenant_id or is_super_admin(user)
    if user.role == "head_of_department":
        return user.department_id is not None and patient.department_id == user.department_id
    if user.role == "doctor":
        return patient.attending_doctor_id == user.id or patient.user_id == user.id
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
    return user.role in WRITE_ROLES | {"viewer", "nurse"}


def anonymize_patient(patient: Patient) -> dict:
    return {
        "id": patient.id,
        "tenant_id": patient.tenant_id,
        "user_id": patient.user_id,
        "department_id": patient.department_id,
        "attending_doctor_id": None,
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
