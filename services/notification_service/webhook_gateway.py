"""Webhook notification gateway.

Sends notification payloads as HTTP POST to user-configured URLs.
Supports custom headers, retryable errors, and JSON payload formatting.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from services.notification_service.models import DeliveryResult, NotificationMessage

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class WebhookGatewayConfig:
    url: str
    headers: dict[str, str] | None = None
    timeout_seconds: float = 10.0
    secret: str = ""  # Optional HMAC signing secret

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("webhook url must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class WebhookGateway:
    name = "webhook"

    def __init__(self, *, config: WebhookGatewayConfig) -> None:
        self.config = config

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        payload = _build_webhook_payload(message)
        headers = dict(self.config.headers or {})
        headers.setdefault("Content-Type", "application/json")
        headers.setdefault("User-Agent", "openTrader-notification/1.0")

        if self.config.secret:
            import hmac
            import hashlib

            body_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
            signature = hmac.new(
                self.config.secret.encode("utf-8"), body_bytes, hashlib.sha256
            ).hexdigest()
            headers["X-Signature-256"] = f"sha256={signature}"

        try:
            response = await asyncio.to_thread(
                _send_webhook,
                url=self.config.url,
                payload=payload,
                headers=headers,
                timeout_seconds=self.config.timeout_seconds,
            )

            if 200 <= response.status_code < 300:
                return DeliveryResult(
                    message_id=message.message_id,
                    gateway=self.name,
                    status="DELIVERED",
                    attempt=1,
                    detail=f"http_{response.status_code}",
                )

            if response.status_code in _RETRYABLE_STATUS_CODES:
                return DeliveryResult(
                    message_id=message.message_id,
                    gateway=self.name,
                    status="RETRYABLE_ERROR",
                    attempt=1,
                    detail=f"http_{response.status_code}",
                )

            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="FAILED_TERMINAL",
                attempt=1,
                detail=f"http_{response.status_code}",
            )

        except (httpx.HTTPError, OSError) as exc:
            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="RETRYABLE_ERROR",
                attempt=1,
                detail=str(exc) or type(exc).__name__,
            )


@dataclass(frozen=True, slots=True)
class WebhookResponse:
    status_code: int
    body: str | None = None


def _build_webhook_payload(message: NotificationMessage) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "user_id": message.user_id,
        "gateway": message.gateway,
        "severity": message.severity.value,
        "title": message.title,
        "body": message.body,
        "metadata": message.metadata,
    }


def _send_webhook(
    *,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> WebhookResponse:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    with httpx.Client(timeout=timeout_seconds, verify=True) as client:
        response = client.post(url, content=body, headers=headers)
        return WebhookResponse(status_code=int(response.status_code), body=response.text)
