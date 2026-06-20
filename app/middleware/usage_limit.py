"""Enforce per-tenant monthly analysis limits before running predictions."""

from __future__ import annotations

import logging
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.middleware.tenant import get_request_tenant_id
from app.services.payment.usage_tracker import check_analysis_limit, get_remaining

logger = logging.getLogger(__name__)

# Paths that consume an analysis credit (POST only).
LIMITED_PATHS = re.compile(r"^/api/analytics/predict/\d+$")


class UsageLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST" and LIMITED_PATHS.match(request.url.path):
            tenant_id = get_request_tenant_id(request)
            if tenant_id is not None and not check_analysis_limit(tenant_id):
                logger.info("Tenant %s exceeded analysis limit", tenant_id)
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": "Месячный лимит анализов исчерпан. Обновите тарифный план.",
                        "remaining": get_remaining(tenant_id),
                        "upgrade_url": "/api/payments/prices",
                    },
                )
        return await call_next(request)
