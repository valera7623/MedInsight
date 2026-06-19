from datetime import datetime, timedelta
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Tenant, User
from app.services.access import ROLES, is_super_admin, require_role
from app.services.audit import log_audit

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

VALID_REGISTER_ROLES = {"doctor", "researcher", "viewer"}


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="doctor")
    subdomain: str | None = None


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
    created_at: datetime

    model_config = {"from_attributes": True}


class TenantPublic(BaseModel):
    id: int
    name: str
    subdomain: str

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


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: Annotated[Session, Depends(get_db)]):
    if data.role not in VALID_REGISTER_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role for self-registration")

    tenant = resolve_tenant_for_auth(db, data.subdomain)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No tenant available")

    existing = (
        db.query(User)
        .filter(User.tenant_id == tenant.id, User.email == data.email)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        tenant_id=tenant.id,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: UserLogin, request: Request, db: Annotated[Session, Depends(get_db)]):
    tenant = resolve_tenant_for_auth(db, data.subdomain)

    user = db.query(User).filter(User.email == data.email).first()
    if user and user.role != "super_admin":
        if tenant and user.tenant_id != tenant.id:
            user = None

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


@router.get("/me", response_model=UserResponse)
def me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
