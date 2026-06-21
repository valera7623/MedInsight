from datetime import datetime, timedelta
from typing import Annotated, Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import rate_limit
from app.models import Department, Tenant, User
from app.services.access import ROLES, is_super_admin, require_role
from app.services.audit import log_audit
from app.services.email import get_email_service

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

VALID_REGISTER_ROLES = {
    "admin",
    "head_of_department",
    "doctor",
    "nurse",
    "researcher",
    "viewer",
}
REGISTER_DEPARTMENT_REQUIRED = frozenset({"head_of_department", "nurse"})
REGISTER_DEPARTMENT_OPTIONAL = frozenset({"doctor", "head_of_department", "nurse"})


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="doctor")
    subdomain: str | None = None
    department_id: int | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    subdomain: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: int | None = None
    role: str


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    tenant_id: int | None
    department_id: int | None = None
    department_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


def user_to_response(user: User, db: Session) -> UserResponse:
    dept_name = None
    if user.department_id:
        dept = db.query(Department).filter(Department.id == user.department_id).first()
        dept_name = dept.name if dept else None
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tenant_id=user.tenant_id,
        department_id=user.department_id,
        department_name=dept_name,
        created_at=user.created_at,
    )


class TenantPublic(BaseModel):
    id: int
    name: str
    subdomain: str

    model_config = {"from_attributes": True}


class DepartmentPublic(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(days=settings.ACCESS_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_email_token(email: str, purpose: str, expire_hours: int) -> str:
    """Signed, short-lived token for email verification / password reset links."""
    expire = datetime.utcnow() + timedelta(hours=expire_hours)
    payload = {"sub": email, "type": purpose, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_tenant_from_subdomain(db: Session, subdomain: str) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.subdomain == subdomain, Tenant.is_active.is_(True)).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


def resolve_tenant_for_auth(db: Session, subdomain: str | None) -> Tenant | None:
    if not settings.TENANT_MODE:
        return db.query(Tenant).filter(Tenant.subdomain == settings.DEFAULT_TENANT_SUBDOMAIN).first()
    if subdomain:
        return get_tenant_from_subdomain(db, subdomain)
    return db.query(Tenant).filter(Tenant.subdomain == settings.DEFAULT_TENANT_SUBDOMAIN).first()


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is blocked")

    request.state.user = user
    return user


def requires_role(*roles: str) -> Callable:
    def dependency(current_user: Annotated[User, Depends(get_current_user)]) -> User:
        require_role(current_user, *roles)
        return current_user

    return dependency


def require_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    require_role(current_user, "admin", "super_admin")
    return current_user


def require_super_admin(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    require_role(current_user, "super_admin")
    return current_user


@router.get("/tenants", response_model=list[TenantPublic])
def list_public_tenants(db: Annotated[Session, Depends(get_db)]):
    if not settings.TENANT_MODE:
        tenant = db.query(Tenant).filter(Tenant.is_active.is_(True)).first()
        return [tenant] if tenant else []
    return db.query(Tenant).filter(Tenant.is_active.is_(True)).order_by(Tenant.name).all()


@router.get("/departments", response_model=list[DepartmentPublic])
def list_public_departments(
    db: Annotated[Session, Depends(get_db)],
    subdomain: str = Query(..., min_length=1),
):
    """Departments for a tenant — used on the registration form (no auth)."""
    tenant = resolve_tenant_for_auth(db, subdomain)
    if not tenant:
        return []
    return (
        db.query(Department)
        .filter(Department.tenant_id == tenant.id)
        .order_by(Department.name)
        .all()
    )


class PasswordResetRequest(BaseModel):
    email: EmailStr
    subdomain: str | None = None


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@rate_limit(
    limit=settings.RATE_LIMIT_REGISTER_PER_HOUR,
    period=3600,
    name="auth_register",
)
def register(
    request: Request,
    data: UserRegister,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
):
    if data.role not in VALID_REGISTER_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role for self-registration")

    tenant = resolve_tenant_for_auth(db, data.subdomain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No tenant available")

    if data.role in REGISTER_DEPARTMENT_REQUIRED and not data.department_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="department_id is required for head_of_department and nurse roles",
        )

    department_id: int | None = None
    if data.department_id is not None:
        if data.role not in REGISTER_DEPARTMENT_OPTIONAL:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="department_id is not used for this role",
            )
        dept = db.query(Department).filter(Department.id == data.department_id).first()
        if not dept or dept.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid department for tenant")
        department_id = dept.id

    existing = (
        db.query(User)
        .filter(User.tenant_id == tenant.id, User.email == data.email)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        tenant_id=tenant.id,
        department_id=department_id,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if settings.EMAIL_VERIFICATION_ENABLED:
        token = create_email_token(user.email, "verify", settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
        background_tasks.add_task(
            get_email_service().send_verification_email, user.email, token, settings.FRONTEND_URL
        )

    return user_to_response(user, db)


@router.post("/login", response_model=TokenResponse)
@rate_limit(
    limit=settings.RATE_LIMIT_LOGIN_PER_MINUTE,
    period=60,
    name="auth_login",
)
def login(data: UserLogin, request: Request, db: Annotated[Session, Depends(get_db)]):
    tenant = resolve_tenant_for_auth(db, data.subdomain)

    candidates = db.query(User).filter(User.email == data.email).all()
    user = next((c for c in candidates if c.role == "super_admin"), None)
    if user is None:
        user = next(
            (c for c in candidates if tenant is None or c.tenant_id == tenant.id),
            None,
        )

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is blocked")

    log_audit(
        db,
        user_id=user.id,
        tenant_id=user.tenant_id,
        action="login",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return TokenResponse(
        access_token=create_access_token(user),
        tenant_id=user.tenant_id,
        role=user.role,
    )


@router.post("/request-reset", status_code=status.HTTP_202_ACCEPTED)
@rate_limit(
    limit=settings.RATE_LIMIT_RESET_PER_HOUR,
    period=3600,
    name="auth_request_reset",
)
def request_reset(
    request: Request,
    data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
):
    """Initiate a password reset.

    Always returns a generic 202 response regardless of whether the email
    exists, to avoid account enumeration. Rate limited to throttle abuse.
    """
    tenant = resolve_tenant_for_auth(db, data.subdomain)
    query = db.query(User).filter(User.email == data.email)
    if tenant is not None:
        query = query.filter(User.tenant_id == tenant.id)
    user = query.first()
    if user:
        log_audit(
            db,
            user_id=user.id,
            tenant_id=user.tenant_id,
            action="password_reset_requested",
            resource_type="user",
            resource_id=user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        token = create_email_token(user.email, "reset", settings.EMAIL_PASSWORD_RESET_EXPIRE_HOURS)
        background_tasks.add_task(
            get_email_service().send_password_reset_email, user.email, token, settings.FRONTEND_URL
        )

    return {"detail": "If the email exists, reset instructions have been sent."}


@router.get("/me", response_model=UserResponse)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return user_to_response(current_user, db)
