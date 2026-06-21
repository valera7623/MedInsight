"""Billing feature flags.

Mirrors the ReportAgent approach: a single ``BILLING_ENABLED`` switch that, when
disabled, turns off all analysis limits and payment checkout (testing /
maintenance mode). Values are read from settings (sourced from the environment),
so flipping ``BILLING_ENABLED`` in ``.env`` + restarting the app applies it.
"""

from __future__ import annotations

from app.config import settings

# Effectively-unlimited quota reported while billing is disabled.
TESTING_UNLIMITED = 999_999


def billing_enabled() -> bool:
    """When False: no report/analysis limits, checkout disabled (testing)."""
    return bool(settings.BILLING_ENABLED)


def stripe_checkout_enabled() -> bool:
    """Stripe checkout requires billing to be on and a configured secret key."""
    if not billing_enabled():
        return False
    return bool((settings.STRIPE_SECRET_KEY or "").strip())


def yookassa_checkout_enabled() -> bool:
    """ЮKassa checkout requires billing to be on and configured credentials."""
    if not billing_enabled():
        return False
    return bool((settings.YOOKASSA_SHOP_ID or "").strip() and (settings.YOOKASSA_SECRET_KEY or "").strip())
