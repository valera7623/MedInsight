"""Tests for SIEM webhook dispatch."""

from unittest.mock import patch

from app.services.audit import log_audit
from app.services.audit_events import AUTH_LOGIN


def test_siem_webhook_called(db_session):
    from tests.conftest import create_tenant, create_user, commit

    tenant = create_tenant(db_session, name="SIEM", subdomain="siem")
    user = create_user(db_session, tenant=tenant, email="siem@example.com")
    commit(db_session)

    with patch("app.config.settings.SIEM_WEBHOOK_ENABLED", True):
        with patch("app.config.settings.SIEM_WEBHOOK_URL", "http://siem.test/hook"):
            with patch("app.services.siem_webhook.httpx.post") as post:
                log_audit(
                    db_session,
                    user_id=user.id,
                    tenant_id=tenant.id,
                    action=AUTH_LOGIN,
                    resource_type="user",
                    resource_id=user.id,
                )
                post.assert_called_once()
