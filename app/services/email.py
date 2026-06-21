"""Asynchronous email notifications via SMTP (aiosmtplib) + Jinja2 templates.

Design goals:
* Never crash the caller — every failure is logged and returns ``False``.
* No-op safely when email is disabled or SMTP is not configured.
* HTML + plain-text multipart for good deliverability.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger("app.services.email")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=False,
)


def _render(template_name: str, **context) -> str:
    return _env.get_template(template_name).render(**context)


class EmailService:
    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_user: str | None = None,
        smtp_password: str | None = None,
        from_email: str | None = None,
        *,
        use_tls: bool | None = None,
        use_ssl: bool | None = None,
        timeout: float | None = None,
    ) -> None:
        self.smtp_host = smtp_host if smtp_host is not None else settings.SMTP_HOST
        self.smtp_port = smtp_port if smtp_port is not None else settings.SMTP_PORT
        self.smtp_user = smtp_user if smtp_user is not None else settings.SMTP_USER
        self.smtp_password = smtp_password if smtp_password is not None else settings.SMTP_PASSWORD
        self.from_email = from_email if from_email is not None else settings.SMTP_FROM
        self.use_tls = use_tls if use_tls is not None else settings.SMTP_USE_TLS
        self.use_ssl = use_ssl if use_ssl is not None else settings.SMTP_USE_SSL
        self.timeout = timeout if timeout is not None else settings.SMTP_TIMEOUT

    @property
    def is_configured(self) -> bool:
        return bool(settings.EMAIL_ENABLED and self.smtp_host and self.from_email)

    async def send_email(self, to: str, subject: str, html: str, text: str | None = None) -> bool:
        if not settings.EMAIL_ENABLED:
            logger.info("Email disabled — skipping send", to=to, subject=subject)
            return False
        if not self.smtp_host:
            logger.warning("SMTP not configured — skipping send", to=to, subject=subject)
            return False

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text or _html_to_text(html))
        message.add_alternative(html, subtype="html")

        try:
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user or None,
                password=self.smtp_password or None,
                start_tls=self.use_tls and not self.use_ssl,
                use_tls=self.use_ssl,
                timeout=self.timeout,
            )
            logger.info("Email sent", to=to, subject=subject)
            return True
        except Exception as exc:  # noqa: BLE001 — email must never break a request
            logger.error("Email send failed", to=to, subject=subject, error=str(exc))
            return False

    # -- high-level templated messages -------------------------------------

    async def send_verification_email(self, email: str, token: str, frontend_url: str | None = None) -> bool:
        base = (frontend_url or settings.FRONTEND_URL).rstrip("/")
        link = f"{base}/verify-email?token={token}"
        ctx = {
            "verification_link": link,
            "expire_hours": settings.EMAIL_VERIFICATION_EXPIRE_HOURS,
            "frontend_url": base,
        }
        html = _render("verification.html", **ctx)
        text = _render("verification.txt", **ctx)
        return await self.send_email(email, "Подтверждение регистрации в MedInsight", html, text)

    async def send_password_reset_email(self, email: str, token: str, frontend_url: str | None = None) -> bool:
        base = (frontend_url or settings.FRONTEND_URL).rstrip("/")
        link = f"{base}/reset-password?token={token}"
        ctx = {
            "reset_link": link,
            "expire_hours": settings.EMAIL_PASSWORD_RESET_EXPIRE_HOURS,
            "frontend_url": base,
        }
        html = _render("reset_password.html", **ctx)
        text = (
            "Сброс пароля MedInsight\n\n"
            f"Чтобы задать новый пароль, перейдите по ссылке (действует {ctx['expire_hours']} ч.):\n"
            f"{link}\n\n"
            "Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо."
        )
        return await self.send_email(email, "Сброс пароля MedInsight", html, text)

    async def send_prediction_ready_email(self, email: str, patient_name: str, prediction_id: int) -> bool:
        base = settings.FRONTEND_URL.rstrip("/")
        link = f"{base}/predictions/{prediction_id}"
        ctx = {
            "patient_name": patient_name,
            "prediction_id": prediction_id,
            "prediction_link": link,
            "frontend_url": base,
        }
        html = _render("prediction_ready.html", **ctx)
        text = (
            "Прогноз готов\n\n"
            f"Прогноз для пациента {patient_name} (ID прогноза: {prediction_id}) готов.\n"
            f"Посмотреть результат: {link}"
        )
        return await self.send_email(email, f"Прогноз готов: {patient_name}", html, text)

    async def send_limit_exceeded_email(self, email: str, plan_type: str, limit: int) -> bool:
        base = settings.FRONTEND_URL.rstrip("/")
        link = f"{base}/billing"
        ctx = {
            "plan_type": plan_type,
            "limit": limit,
            "upgrade_link": link,
            "frontend_url": base,
        }
        html = _render("limit_exceeded.html", **ctx)
        text = (
            "Лимит анализов исчерпан\n\n"
            f"Вы достигли месячного лимита тарифа «{plan_type}» ({limit} анализов).\n"
            f"Обновите тариф, чтобы продолжить: {link}"
        )
        return await self.send_email(email, "Лимит анализов MedInsight исчерпан", html, text)


def _html_to_text(html: str) -> str:
    """Very small HTML→text fallback for clients without HTML support."""
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_service: EmailService | None = None


def get_email_service() -> EmailService:
    global _service
    if _service is None:
        _service = EmailService()
    return _service
