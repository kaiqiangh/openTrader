"""Tests for email and webhook notification gateways."""

from __future__ import annotations

import pytest

from services.notification_service.models import NotificationMessage, NotificationSeverity


def _make_message(**overrides: object) -> NotificationMessage:
    defaults = dict(
        message_id="msg-test-1",
        user_id="ops",
        gateway="test",
        severity=NotificationSeverity.WARNING,
        title="Test Alert",
        body="Something happened",
        metadata={"trace_id": "abc123", "decision_id": "def456"},
    )
    defaults.update(overrides)
    return NotificationMessage(**defaults)  # type: ignore[arg-type]


class TestEmailGateway:
    def test_render_email_includes_severity(self) -> None:
        from services.notification_service.email_gateway import _render_email

        msg = _make_message(severity=NotificationSeverity.CRITICAL)
        subject, body_html, body_text = _render_email(msg)

        assert "[CRITICAL]" in subject
        assert "CRITICAL" in body_html
        assert "CRITICAL" in body_text
        assert "abc123" in body_text  # trace_id

    def test_render_email_subject_format(self) -> None:
        from services.notification_service.email_gateway import _render_email

        msg = _make_message(title="Order Filled", severity=NotificationSeverity.INFO)
        subject, _, _ = _render_email(msg)

        assert subject == "[INFO] Order Filled"

    def test_resolve_recipients_from_metadata(self) -> None:
        from services.notification_service.email_gateway import _resolve_recipients

        msg = _make_message(metadata={"email_recipients": "a@b.com, c@d.com"})
        result = _resolve_recipients(message=msg, defaults=("default@x.com",))
        assert result == ["a@b.com", "c@d.com"]

    def test_resolve_recipients_uses_defaults(self) -> None:
        from services.notification_service.email_gateway import _resolve_recipients

        msg = _make_message(metadata={})
        result = _resolve_recipients(message=msg, defaults=("default@x.com",))
        assert result == ["default@x.com"]

    def test_config_requires_smtp_host(self) -> None:
        from services.notification_service.email_gateway import EmailGatewayConfig

        with pytest.raises(ValueError, match="smtp_host"):
            EmailGatewayConfig(
                smtp_host="", from_address="a@b.com", default_recipients=("x@y.com",)
            )


class TestWebhookGateway:
    def test_build_payload_includes_all_fields(self) -> None:
        from services.notification_service.webhook_gateway import _build_webhook_payload

        msg = _make_message()
        payload = _build_webhook_payload(msg)

        assert payload["message_id"] == "msg-test-1"
        assert payload["severity"] == "WARNING"
        assert payload["title"] == "Test Alert"
        assert payload["metadata"]["trace_id"] == "abc123"

    def test_config_requires_url(self) -> None:
        from services.notification_service.webhook_gateway import WebhookGatewayConfig

        with pytest.raises(ValueError, match="url"):
            WebhookGatewayConfig(url="")

    def test_config_valid(self) -> None:
        from services.notification_service.webhook_gateway import WebhookGatewayConfig

        config = WebhookGatewayConfig(url="https://example.com/hook", secret="s3cret")
        assert config.url == "https://example.com/hook"
        assert config.secret == "s3cret"


class TestGatewayDispatchWithNewGateways:
    @pytest.mark.asyncio
    async def test_webhook_dispatch_success(self) -> None:
        """Test that webhook gateway integrates with GatewayDispatcher."""
        from unittest.mock import MagicMock, patch
        from services.notification_service.gateway_dispatch import GatewayDispatcher
        from services.notification_service.webhook_gateway import (
            WebhookGateway,
            WebhookGatewayConfig,
            WebhookResponse,
        )

        gateway = WebhookGateway(config=WebhookGatewayConfig(url="https://example.com/hook"))

        # Mock the HTTP call
        with patch("services.notification_service.webhook_gateway._send_webhook") as mock_send:
            mock_send.return_value = WebhookResponse(status_code=200)

            dispatcher = GatewayDispatcher(gateways={"webhook": gateway})
            msg = _make_message(gateway="webhook")
            event = MagicMock()
            event.notification_event_id = "evt-1"

            results = await dispatcher.dispatch(event=event, messages=(msg,))
            assert len(results) == 1
            assert results[0].status == "DELIVERED"

    @pytest.mark.asyncio
    async def test_webhook_dispatch_retryable_then_success(self) -> None:
        """Test that 503 is retried and eventually succeeds."""
        from unittest.mock import MagicMock, patch
        from services.notification_service.gateway_dispatch import GatewayDispatcher
        from services.notification_service.webhook_gateway import (
            WebhookGateway,
            WebhookGatewayConfig,
            WebhookResponse,
        )

        gateway = WebhookGateway(config=WebhookGatewayConfig(url="https://example.com/hook"))

        with patch("services.notification_service.webhook_gateway._send_webhook") as mock_send:
            mock_send.side_effect = [
                WebhookResponse(status_code=503),
                WebhookResponse(status_code=200),
            ]

            dispatcher = GatewayDispatcher(
                gateways={"webhook": gateway}, max_attempts=3, backoff_base_seconds=0.0
            )
            msg = _make_message(gateway="webhook")
            event = MagicMock()
            event.notification_event_id = "evt-1"

            results = await dispatcher.dispatch(event=event, messages=(msg,))
            assert results[0].status == "DELIVERED"
            assert results[0].attempt == 2
