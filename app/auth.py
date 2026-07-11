from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable

from app.models._time import utc_now

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
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
from app.services.audit_events import (
    AUTH_ACCOUNT_LOCKED,
    AUTH_LOGIN,
    AUTH_LOGIN_FAILED,
    AUTH_LOGOUT,
    AUTH_SESSION_REVOKED,
)
from app.services.email import get_email_service
from app.services.login_lockout import clear_failed_logins, is_locked, record_failed_login
from app.services.mfa_policy import mfa_required_for_user
from app.services.password_policy import PasswordPolicyError, validate_password
from app.services.session_store import (
    create_session,
    list_sessions,
    revoke_all_sessions,
    revoke_session,
    session_valid,
)

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

# Self-registration: elevated roles (admin, head_of_department) are admin-provisioned only.
VALID_REGISTER_ROLES = frozenset({"doctor", "nurse", "researcher", "viewer"})
REGISTER_DEPARTMENT_REQUIRED = frozenset({"nurse"})
REGISTER_DEPARTMENT_OPTIONAL = frozenset({"doctor", "nurse"})


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="doctor")
    subdomain: str | None = None
    department_id: int | None = None


class LogoutRequest(BaseModel):
    refresh_token: str | None = None
    all_devices: bool = False


class SessionInfo(BaseModel):
    jti: str
    created_at: int
    user_agent: str | None = None
    ip_address: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    subdomain: str | None = None
    totp_code: str | None = None


class AuthCapabilities(BaseModel):
    password_reset_available: bool
    fhir_enabled: bool
    siem_export_enabled: bool
    telegram_bot_enabled: bool
    telegram_bot_username: str | None = None
    totp_available: bool = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    tenant_id: int | None = None
    role: str
    demo_mode: bool = False
    totp_required: bool = False


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    tenant_id: int | None
    department_id: int | None = None
    department_name: str | None = None
    email_verified: bool = True
    created_at: datetime
    demo_mode: bool = False

    model_config = {"from_attributes": True}


class RegisterResponse(UserResponse):
    email_verification_required: bool = False


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
        email_verified=bool(getattr(user, "email_verified", True)),
        created_at=user.created_at,
        demo_mode=bool(settings.DEMO_MODE),
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


def user_token_version(user: User) -> int:
    return int(getattr(user, "token_version", 0) or 0)


def bump_token_version(user: User) -> None:
    user.token_version = user_token_version(user) + 1


def create_access_token(user: User) -> str:
    expire = utc_now() + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "role": user.role,
        "type": "access",
        "token_version": user_token_version(user),
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user: User, *, jti: str | None = None) -> str:
    return create_refresh_token_with_jti(user, jti or create_session(user.id))


def create_refresh_token_with_jti(user: User, jti: str) -> str:
    expire = utc_now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "role": user.role,
        "type": "refresh",
        "token_version": user_token_version(user),
        "jti": jti,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _set_auth_cookies(response: Response, access: str, refresh: str | None) -> None:
    if not settings.AUTH_COOKIE_ENABLED:
        return
    secure = settings.AUTH_COOKIE_SECURE or settings.ENVIRONMENT == "production"
    response.set_cookie(
        settings.AUTH_ACCESS_COOKIE_NAME,
        access,
        httponly=True,
        secure=secure,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        path="/",
    )
    if refresh:
        response.set_cookie(
            settings.AUTH_REFRESH_COOKIE_NAME,
            refresh,
            httponly=True,
            secure=secure,
            samesite=settings.AUTH_COOKIE_SAMESITE,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            path="/api/auth",
        )


def _clear_auth_cookies(response: Response) -> None:
    if not settings.AUTH_COOKIE_ENABLED:
        return
    response.delete_cookie(settings.AUTH_ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(settings.AUTH_REFRESH_COOKIE_NAME, path="/api/auth")


def _resolve_bearer_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is not None:
        return credentials.credentials
    if settings.AUTH_COOKIE_ENABLED:
        return request.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
    return None


def create_email_token(email: str, purpose: str, expire_hours: int, *, tenant_id: int | None = None) -> str:
    """Signed, short-lived token for email verification / password reset links."""
    expire = utc_now() + timedelta(hours=expire_hours)
    payload: dict = {"sub": email, "type": purpose, "exp": expire}
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_email_token(token: str, *, purpose: str) -> tuple[str, int | None]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        ) from exc
    if payload.get("type") != purpose:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token type")
    email = payload.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token payload")
    tenant_id = payload.get("tenant_id")
    return str(email), int(tenant_id) if tenant_id is not None else None


def email_verification_required() -> bool:
    return bool(settings.EMAIL_VERIFICATION_ENABLED and get_email_service().is_configured)


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
    token = _resolve_bearer_token(request, credentials)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
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
    token_ver = payload.get("token_version", 0)
    if int(token_ver) != user_token_version(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")

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


@router.get("/capabilities", response_model=AuthCapabilities)
def auth_capabilities():
    email_ok = get_email_service().is_configured
    return AuthCapabilities(
        password_reset_available=bool(email_ok),
        fhir_enabled=bool(settings.FHIR_ENABLED),
        siem_export_enabled=bool(settings.SIEM_EXPORT_ENABLED),
        telegram_bot_enabled=bool(settings.TELEGRAM_BOT_ENABLED),
        telegram_bot_username=settings.TELEGRAM_BOT_USERNAME or None,
    )


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


class ResendVerificationRequest(BaseModel):
    email: EmailStr
    subdomain: str | None = None


class MessageResponse(BaseModel):
    detail: str
    email_verified: bool | None = None


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
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
            detail="department_id is required for nurse role",
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

    try:
        validate_password(data.password, email=data.email)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    needs_verification = email_verification_required()
    user = User(
        tenant_id=tenant.id,
        department_id=department_id,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        email_verified=not needs_verification,
        email_verified_at=utc_now() if not needs_verification else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    if needs_verification:
        token = create_email_token(
            user.email, "verify", settings.EMAIL_VERIFICATION_EXPIRE_HOURS, tenant_id=user.tenant_id
        )
        background_tasks.add_task(
            get_email_service().send_verification_email, user.email, token, settings.FRONTEND_URL
        )

    base = user_to_response(user, db)
    return RegisterResponse(
        **base.model_dump(),
        email_verification_required=needs_verification,
    )


@router.post("/login", response_model=TokenResponse)
@rate_limit(
    limit=settings.RATE_LIMIT_LOGIN_PER_MINUTE,
    period=60,
    name="auth_login",
)
def login(data: UserLogin, request: Request, response: Response, db: Annotated[Session, Depends(get_db)]):
    tenant = resolve_tenant_for_auth(db, data.subdomain)

    candidates = db.query(User).filter(User.email == data.email).all()
    user = next((c for c in candidates if c.role == "super_admin"), None)
    if user is None:
        user = next(
            (c for c in candidates if tenant is None or c.tenant_id == tenant.id),
            None,
        )

    if user:
        locked, retry = is_locked(user.id)
        if locked:
            log_audit(
                db,
                user_id=user.id,
                tenant_id=user.tenant_id,
                action=AUTH_ACCOUNT_LOCKED,
                resource_type="user",
                resource_id=user.id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked. Retry after {retry}s.",
            )

    if not user or not verify_password(data.password, user.password_hash):
        if user:
            fails, now_locked = record_failed_login(user.id)
            log_audit(
                db,
                user_id=user.id,
                tenant_id=user.tenant_id,
                action=AUTH_LOGIN_FAILED,
                resource_type="user",
                resource_id=user.id,
                details={"fail_count": fails, "locked": now_locked},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    clear_failed_logins(user.id)

    if user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is blocked")

    if mfa_required_for_user(user, tenant) and not user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="2FA is required for your role. Enable TOTP in account settings.",
        )
    if (
        email_verification_required()
        and user.role != "super_admin"
        and not getattr(user, "email_verified", True)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Подтвердите email. Проверьте почту или запросите повторную отправку письма.",
        )

    if user.totp_enabled:
        from app.services.totp import consume_backup_code, verify_totp

        if not data.totp_code:
            return TokenResponse(
                access_token="",
                refresh_token=None,
                tenant_id=user.tenant_id,
                role=user.role,
                demo_mode=bool(settings.DEMO_MODE),
                totp_required=True,
            )
        code_ok = verify_totp(user.totp_secret or "", data.totp_code)
        if not code_ok:
            used, remaining = consume_backup_code(user.totp_backup_codes, data.totp_code)
            if used:
                user.totp_backup_codes = remaining
                db.commit()
            else:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code")

    log_audit(
        db,
        user_id=user.id,
        tenant_id=user.tenant_id,
        action=AUTH_LOGIN,
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    jti = create_session(
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    access = create_access_token(user)
    refresh = create_refresh_token_with_jti(user, jti)
    _set_auth_cookies(response, access, refresh)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        tenant_id=user.tenant_id,
        role=user.role,
        demo_mode=bool(settings.DEMO_MODE),
    )


@router.post("/refresh", response_model=TokenResponse)
@rate_limit(
    limit=settings.RATE_LIMIT_LOGIN_PER_MINUTE,
    period=60,
    name="auth_refresh",
)
def refresh_token(
    data: RefreshTokenRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    token = data.refresh_token
    if not token and settings.AUTH_COOKIE_ENABLED:
        token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user_id = payload.get("sub")
    jti = payload.get("jti")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or user.is_blocked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or blocked")
    token_ver = payload.get("token_version", 0)
    if int(token_ver) != user_token_version(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked")
    if jti and not session_valid(str(jti), user.id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session revoked")

    new_jti = create_session(
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    if jti:
        revoke_session(str(jti), user.id)
    access = create_access_token(user)
    refresh = create_refresh_token_with_jti(user, new_jti)
    _set_auth_cookies(response, access, refresh)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        tenant_id=user.tenant_id,
        role=user.role,
        demo_mode=bool(settings.DEMO_MODE),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    data: LogoutRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    token = data.refresh_token
    if not token and settings.AUTH_COOKIE_ENABLED:
        token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if data.all_devices:
        count = revoke_all_sessions(current_user.id)
        bump_token_version(current_user)
        db.commit()
        log_audit(
            db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action=AUTH_SESSION_REVOKED,
            resource_type="user",
            resource_id=current_user.id,
            details={"all_devices": True, "count": count},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    elif token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            jti = payload.get("jti")
            if jti:
                revoke_session(str(jti), current_user.id)
        except JWTError:
            pass
        log_audit(
            db,
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action=AUTH_LOGOUT,
            resource_type="user",
            resource_id=current_user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    _clear_auth_cookies(response)
    return MessageResponse(detail="Logged out")


@router.get("/sessions", response_model=list[SessionInfo])
def my_sessions(current_user: Annotated[User, Depends(get_current_user)]):
    return [SessionInfo(**s) for s in list_sessions(current_user.id)]


@router.delete("/sessions/{jti}", response_model=MessageResponse)
def revoke_my_session(
    jti: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    revoke_session(jti, current_user.id)
    log_audit(
        db,
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action=AUTH_SESSION_REVOKED,
        resource_type="user",
        resource_id=current_user.id,
        details={"jti": jti},
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(detail="Session revoked")


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
        token = create_email_token(
            user.email, "reset", settings.EMAIL_PASSWORD_RESET_EXPIRE_HOURS, tenant_id=user.tenant_id
        )
        background_tasks.add_task(
            get_email_service().send_password_reset_email, user.email, token, settings.FRONTEND_URL
        )

    return {"detail": "If the email exists, reset instructions have been sent."}


@router.post("/reset-password", response_model=MessageResponse)
@rate_limit(
    limit=settings.RATE_LIMIT_RESET_PER_HOUR,
    period=3600,
    name="auth_reset_password",
)
def reset_password(
    request: Request,
    data: ResetPasswordRequest,
    db: Annotated[Session, Depends(get_db)],
):
    email, tenant_id = decode_email_token(data.token, purpose="reset")
    query = db.query(User).filter(User.email == email)
    if tenant_id is not None:
        query = query.filter(User.tenant_id == tenant_id)
    user = query.first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    try:
        validate_password(data.new_password, email=user.email)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    user.password_hash = hash_password(data.new_password)
    bump_token_version(user)
    db.commit()
    log_audit(
        db,
        user_id=user.id,
        tenant_id=user.tenant_id,
        action="password_reset_completed",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return MessageResponse(detail="Password updated successfully")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    db: Annotated[Session, Depends(get_db)],
    token: str = Query(..., min_length=10),
):
    email, tenant_id = decode_email_token(token, purpose="verify")
    query = db.query(User).filter(User.email == email)
    if tenant_id is not None:
        query = query.filter(User.tenant_id == tenant_id)
    user = query.first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.email_verified:
        return MessageResponse(detail="Email already verified", email_verified=True)

    user.email_verified = True
    user.email_verified_at = utc_now()
    db.commit()
    log_audit(
        db,
        user_id=user.id,
        tenant_id=user.tenant_id,
        action="email_verified",
        resource_type="user",
        resource_id=user.id,
    )
    return MessageResponse(detail="Email verified successfully", email_verified=True)


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED, response_model=MessageResponse)
@rate_limit(
    limit=settings.RATE_LIMIT_RESET_PER_HOUR,
    period=3600,
    name="auth_resend_verification",
)
def resend_verification(
    request: Request,
    data: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
):
    """Resend verification email (generic response to avoid account enumeration)."""
    if not email_verification_required():
        return MessageResponse(detail="Email verification is not required")

    tenant = resolve_tenant_for_auth(db, data.subdomain)
    query = db.query(User).filter(User.email == data.email)
    if tenant is not None:
        query = query.filter(User.tenant_id == tenant.id)
    user = query.first()

    if user and not user.email_verified:
        token = create_email_token(
            user.email, "verify", settings.EMAIL_VERIFICATION_EXPIRE_HOURS, tenant_id=user.tenant_id
        )
        background_tasks.add_task(
            get_email_service().send_verification_email, user.email, token, settings.FRONTEND_URL
        )
        log_audit(
            db,
            user_id=user.id,
            tenant_id=user.tenant_id,
            action="verification_resent",
            resource_type="user",
            resource_id=user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    return MessageResponse(detail="If the account exists and is unverified, a verification email was sent.")


@router.get("/me", response_model=UserResponse)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    return user_to_response(current_user, db)
