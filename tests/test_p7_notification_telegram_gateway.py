from __future__ import annotations

from dataclasses import dataclass

import pytest

from services.notification_service.models import NotificationMessage, NotificationSeverity
from services.notification_service.telegram_gateway import (
    TelegramGateway,
    TelegramGatewayConfig,
    TelegramSendResult,
    render_telegram_message_text,
)


def _message() -> NotificationMessage:
    return NotificationMessage(
        message_id="msg-1",
        user_id="ops",
        gateway="telegram",
        severity=NotificationSeverity.WARNING,
        title="[WARNING] risk.alert_(test)",
        body="event=risk.guard reason=drawdown_(5%)",
        metadata={"trace_id": "trace-1", "decision_id": "decision-1"},
    )


def test_render_telegram_message_text_escapes_markdown_v2_reserved_chars() -> None:
    rendered = render_telegram_message_text(_message())
    assert "\\[" in rendered
    assert "\\(" in rendered
    assert "\\_" in rendered
    assert "trace\\-1" in rendered
    assert "decision\\-1" in rendered


@dataclass(slots=True)
class _SenderStub:
    status_code: int

    async def __call__(self, *, token: str, chat_id: str, text: str, timeout_seconds: float) -> TelegramSendResult:
        return TelegramSendResult(status_code=self.status_code, body={"ok": self.status_code == 200})


@pytest.mark.asyncio
async def test_telegram_gateway_maps_retryable_and_terminal_statuses() -> None:
    config = TelegramGatewayConfig(bot_token="token", default_chat_id="123")
    retryable_gateway = TelegramGateway(config=config, sender=_SenderStub(status_code=503))
    terminal_gateway = TelegramGateway(config=config, sender=_SenderStub(status_code=400))

    retryable = await retryable_gateway.send(_message())
    terminal = await terminal_gateway.send(_message())

    assert retryable.status == "RETRYABLE_ERROR"
    assert terminal.status == "FAILED_TERMINAL"


def test_markdown_v2_reserved_is_set():
    """_MARKDOWN_V2_RESERVED should be a set for O(1) lookup."""
    from services.notification_service.telegram_gateway import _MARKDOWN_V2_RESERVED
    assert isinstance(_MARKDOWN_V2_RESERVED, set)
