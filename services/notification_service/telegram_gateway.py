from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import asyncio
import json
import os
from typing import Any, Protocol
from urllib import error, request

from services.notification_service.models import DeliveryResult, NotificationMessage
from services.shared.runtime.env_loader import load_dotenv_file

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MARKDOWN_V2_RESERVED = r"_*[]()~`>#+-=|{}.!"


@dataclass(frozen=True, slots=True)
class TelegramGatewayConfig:
    bot_token: str
    default_chat_id: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.bot_token.strip():
            raise ValueError("bot_token must be non-empty")
        if not self.default_chat_id.strip():
            raise ValueError("default_chat_id must be non-empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class TelegramSendResult:
    status_code: int
    body: Mapping[str, Any] | None
    error: str | None = None


class TelegramSender(Protocol):
    async def __call__(
        self,
        *,
        token: str,
        chat_id: str,
        text: str,
        timeout_seconds: float,
    ) -> TelegramSendResult: ...


class TelegramGateway:
    name = "telegram"

    def __init__(
        self,
        *,
        config: TelegramGatewayConfig,
        sender: TelegramSender | None = None,
    ) -> None:
        self.config = config
        self._sender = sender or _default_sender

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        target_chat_id = _resolve_chat_id(message=message, default_chat_id=self.config.default_chat_id)
        text = render_telegram_message_text(message)

        response = await self._sender(
            token=self.config.bot_token,
            chat_id=target_chat_id,
            text=text,
            timeout_seconds=self.config.timeout_seconds,
        )

        if response.status_code == 200 and bool((response.body or {}).get("ok", True)):
            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="DELIVERED",
                attempt=1,
                detail=None,
            )

        if response.status_code == 0 or response.status_code in _RETRYABLE_STATUS_CODES:
            detail = response.error or f"telegram_http_{response.status_code or 'network'}"
            return DeliveryResult(
                message_id=message.message_id,
                gateway=self.name,
                status="RETRYABLE_ERROR",
                attempt=1,
                detail=detail,
            )

        return DeliveryResult(
            message_id=message.message_id,
            gateway=self.name,
            status="FAILED_TERMINAL",
            attempt=1,
            detail=response.error or f"telegram_http_{response.status_code}",
        )


def render_telegram_message_text(message: NotificationMessage) -> str:
    title = _escape_markdown_v2(message.title)
    body = _escape_markdown_v2(message.body)
    severity = _escape_markdown_v2(message.severity.value)
    user_id = _escape_markdown_v2(message.user_id)
    trace_id = _escape_markdown_v2(str(message.metadata.get("trace_id", "n/a")))
    decision_id = _escape_markdown_v2(str(message.metadata.get("decision_id", "n/a")))

    return (
        f"*{title}*\n"
        f"{body}\n\n"
        f"*severity:* `{severity}`\n"
        f"*user:* `{user_id}`\n"
        f"*trace:* `{trace_id}`\n"
        f"*decision:* `{decision_id}`"
    )


def load_telegram_gateway_from_env() -> TelegramGateway | None:
    load_dotenv_file()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    default_chat_id = os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "").strip()
    if not bot_token or not default_chat_id:
        return None

    timeout_seconds = float(os.getenv("NOTIFY_GATEWAY_TIMEOUT_SECONDS", "10.0"))
    config = TelegramGatewayConfig(
        bot_token=bot_token,
        default_chat_id=default_chat_id,
        timeout_seconds=timeout_seconds,
    )
    return TelegramGateway(config=config)


def _resolve_chat_id(*, message: NotificationMessage, default_chat_id: str) -> str:
    metadata_chat_id = str(message.metadata.get("chat_id", "")).strip()
    if metadata_chat_id:
        return metadata_chat_id
    return default_chat_id


def _escape_markdown_v2(value: str) -> str:
    escaped = []
    for char in value:
        if char in _MARKDOWN_V2_RESERVED:
            escaped.append(f"\\{char}")
        else:
            escaped.append(char)
    return "".join(escaped)


async def _default_sender(
    *,
    token: str,
    chat_id: str,
    text: str,
    timeout_seconds: float,
) -> TelegramSendResult:
    return await asyncio.to_thread(
        _send_http_request,
        token=token,
        chat_id=chat_id,
        text=text,
        timeout_seconds=timeout_seconds,
    )


def _send_http_request(
    *,
    token: str,
    chat_id: str,
    text: str,
    timeout_seconds: float,
) -> TelegramSendResult:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            body = _decode_json(raw)
            status_code = int(getattr(response, "status", 200))
            return TelegramSendResult(status_code=status_code, body=body)
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        body = _decode_json(raw)
        return TelegramSendResult(
            status_code=int(exc.code),
            body=body,
            error=str(exc),
        )
    except (OSError, ValueError) as exc:
        return TelegramSendResult(status_code=0, body=None, error=str(exc))


def _decode_json(raw: str) -> Mapping[str, Any] | None:
    if not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}
    if isinstance(payload, dict):
        return payload
    return {"raw": payload}
