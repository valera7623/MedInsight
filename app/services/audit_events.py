"""Standard audit event taxonomy for SIEM and compliance mapping."""

from __future__ import annotations

# Authentication
AUTH_LOGIN = "auth.login"
AUTH_LOGIN_FAILED = "auth.login_failed"
AUTH_LOGIN_SSO = "auth.login_sso"
AUTH_LOGOUT = "auth.logout"
AUTH_REFRESH = "auth.refresh"
AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
AUTH_PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"
AUTH_EMAIL_VERIFIED = "auth.email_verified"
AUTH_SESSION_REVOKED = "auth.session_revoked"
AUTH_ACCOUNT_LOCKED = "auth.account_locked"

# Data
DATA_EXPORT = "data.export"
DATA_IMPORT = "data.import"
DATA_DELETE = "data.delete"
DSAR_EXPORT = "dsar.export"
DSAR_ERASURE = "dsar.erasure"

# Security
SECURITY_KEY_ROTATE = "security.key_rotate"
SECURITY_MFA_ENABLED = "security.mfa_enabled"
SECURITY_MFA_DISABLED = "security.mfa_disabled"

# Admin
ADMIN_USER_CREATE = "admin.user_create"
ADMIN_USER_BLOCK = "admin.user_block"
ADMIN_TENANT_UPDATE = "admin.tenant_update"

ALL_EVENTS = frozenset(
    {
        AUTH_LOGIN,
        AUTH_LOGIN_FAILED,
        AUTH_LOGIN_SSO,
        AUTH_LOGOUT,
        AUTH_REFRESH,
        AUTH_PASSWORD_RESET_REQUESTED,
        AUTH_PASSWORD_RESET_COMPLETED,
        AUTH_EMAIL_VERIFIED,
        AUTH_SESSION_REVOKED,
        AUTH_ACCOUNT_LOCKED,
        DATA_EXPORT,
        DATA_IMPORT,
        DATA_DELETE,
        DSAR_EXPORT,
        DSAR_ERASURE,
        SECURITY_KEY_ROTATE,
        SECURITY_MFA_ENABLED,
        SECURITY_MFA_DISABLED,
        ADMIN_USER_CREATE,
        ADMIN_USER_BLOCK,
        ADMIN_TENANT_UPDATE,
    }
)
