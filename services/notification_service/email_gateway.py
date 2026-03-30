"""Email notification gateway via SMTP.

Sends notification emails using configurable SMTP server.
Supports TLS, authentication, and multiple recipients.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from services.notification_service.models import DeliveryResult, NotificationMessage
from services.shared.runtime.env_loader import load_dotenv_file

logger = logging.getLogger(__name__)

_SEVERITY_COLORS = {
    "INFO": "#17d6a5",
    "WARNING": "#f0ad4e",
    "CRITICAL": "#dc3545",
}


@dataclass(frozen=True, slots=True)
class EmailGatewayConfig:
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    use_tls: bool = True
    from_address: str = ""
    default_recipients: tuple[str, ...] = ()
    timeout_seconds: float = 15.0

    def __post_init__(self) -> None:
        if not self.smtp_host.strip():
            raise ValueError("smtp_host must be non-empty")
        if not self.from_address.strip():
            raise ValueError("from_address must be non-empty")
        if not self.default_recipients:
            raise ValueError("default_recipients must be non-empty")


class EmailGateway:
    name = "email"

    def __init__(self, *, config: EmailGatewayConfig) -> None:
        self.config = config

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        recipients = _resolve_recipients(message=message, defaults=self.config.default_recipients)
        subject, body_html, body_text = _render_email(message)

        try:
            await asyncio.to_thread(
                _send_smtp,
                config=self.config,
                recipients=recipients,
                subject=subject,
                body_html=body_html,
                body_text=body_text,
            )
            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="DELIVERED",
                attempt=1,
                detail=None,
            )
        except smtplib.SMTPResponseException as exc:
            if exc.smtp_code >= 500:
                return DeliveryResult(
                    message_id=message.message_id,
                    gateway=self.name,
                    status="FAILED_TERMINAL",
                    attempt=1,
                    detail=f"smtp_error_{exc.smtp_code}",
                )
            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="RETRYABLE_ERROR",
                attempt=1,
                detail=f"smtp_error_{exc.smtp_code}",
            )
        except (smtplib.SMTPException, OSError) as exc:
            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="RETRYABLE_ERROR",
                attempt=1,
                detail=str(exc) or type(exc).__name__,
            )


def load_email_gateway_from_env() -> EmailGateway | None:
    load_dotenv_file()
    smtp_host = os.getenv("EMAIL_SMTP_HOST", "").strip()
    from_address = os.getenv("EMAIL_FROM_ADDRESS", "").strip()
    recipients_raw = os.getenv("EMAIL_DEFAULT_RECIPIENTS", "").strip()

    if not smtp_host or not from_address or not recipients_raw:
        return None

    recipients = tuple(r.strip() for r in recipients_raw.split(",") if r.strip())
    config = EmailGatewayConfig(
        smtp_host=smtp_host,
        smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "587")),
        smtp_username=os.getenv("EMAIL_SMTP_USERNAME", "").strip(),
        smtp_password=os.getenv("EMAIL_SMTP_PASSWORD", "").strip(),
        use_tls=os.getenv("EMAIL_USE_TLS", "true").strip().lower() in {"1", "true", "yes"},
        from_address=from_address,
        default_recipients=recipients,
        timeout_seconds=float(os.getenv("EMAIL_TIMEOUT_SECONDS", "15.0")),
    )
    return EmailGateway(config=config)


def _resolve_recipients(*, message: NotificationMessage, defaults: tuple[str, ...]) -> list[str]:
    metadata_recipients = str(message.metadata.get("email_recipients", "")).strip()
    if metadata_recipients:
        return [r.strip() for r in metadata_recipients.split(",") if r.strip()]
    return list(defaults)


def _render_email(message: NotificationMessage) -> tuple[str, str, str]:
    severity = message.severity.value
    color = _SEVERITY_COLORS.get(severity, "#6c757d")
    subject = f"[{severity}] {message.title}"

    body_text = (
        f"{message.title}\n"
        f"{'=' * 40}\n\n"
        f"{message.body}\n\n"
        f"Severity: {severity}\n"
        f"Trace ID: {message.metadata.get('trace_id', 'n/a')}\n"
        f"Decision ID: {message.metadata.get('decision_id', 'n/a')}\n"
    )

    body_html = f"""
    <html><body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="border-left: 4px solid {color}; padding: 12px 16px; background: #f8f9fa; margin-bottom: 16px;">
            <h2 style="margin: 0 0 8px 0; color: #212529;">{message.title}</h2>
            <span style="background: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">{severity}</span>
        </div>
        <div style="padding: 16px; background: #ffffff; border: 1px solid #dee2e6; border-radius: 8px;">
            <p style="color: #495057; line-height: 1.6;">{message.body}</p>
        </div>
        <div style="margin-top: 16px; padding: 12px; background: #f1f3f5; border-radius: 8px; font-size: 13px; color: #6c757d;">
            <p style="margin: 4px 0;"><strong>Trace:</strong> {message.metadata.get("trace_id", "n/a")}</p>
            <p style="margin: 4px 0;"><strong>Decision:</strong> {message.metadata.get("decision_id", "n/a")}</p>
        </div>
    </body></html>
    """
    return subject, body_html, body_text


def _send_smtp(
    *,
    config: EmailGatewayConfig,
    recipients: list[str],
    subject: str,
    body_html: str,
    body_text: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.from_address
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    if config.use_tls:
        with smtplib.SMTP(
            config.smtp_host, config.smtp_port, timeout=config.timeout_seconds
        ) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if config.smtp_username and config.smtp_password:
                server.login(config.smtp_username, config.smtp_password)
            server.sendmail(config.from_address, recipients, msg.as_string())
    else:
        with smtplib.SMTP(
            config.smtp_host, config.smtp_port, timeout=config.timeout_seconds
        ) as server:
            if config.smtp_username and config.smtp_password:
                server.login(config.smtp_username, config.smtp_password)
            server.sendmail(config.from_address, recipients, msg.as_string())
