from services.notification_service.event_intake import NotificationEventIntake
from services.notification_service.gateway_dispatch import GatewayDispatcher, InMemoryGateway
from services.notification_service.models import (
    DeliveryResult,
    NotificationEvent,
    NotificationMessage,
    NotificationPreference,
    NotificationProcessingResult,
    NotificationSeverity,
)
from services.notification_service.policy_router import NotificationPolicyRouter
from services.notification_service.publishers import NotificationEventBridge
from services.notification_service.service import NotificationService
from services.notification_service.telegram_gateway import (
    TelegramGateway,
    TelegramGatewayConfig,
    TelegramSendResult,
    load_telegram_gateway_from_env,
    render_telegram_message_text,
)
from services.notification_service.observability import (
    NotificationObservabilityCollector,
    NotificationTraceSpan,
    NotificationDeliveryLog,
)
from services.notification_service.settings import (
    NotificationSettingsError,
    NotificationWorkerSettings,
    load_notification_worker_settings,
)

__all__ = [
    "NotificationEvent",
    "NotificationMessage",
    "NotificationPreference",
    "NotificationSeverity",
    "DeliveryResult",
    "NotificationProcessingResult",
    "NotificationEventIntake",
    "NotificationPolicyRouter",
    "GatewayDispatcher",
    "InMemoryGateway",
    "TelegramGateway",
    "TelegramGatewayConfig",
    "TelegramSendResult",
    "render_telegram_message_text",
    "load_telegram_gateway_from_env",
    "NotificationObservabilityCollector",
    "NotificationTraceSpan",
    "NotificationDeliveryLog",
    "NotificationSettingsError",
    "NotificationWorkerSettings",
    "load_notification_worker_settings",
    "NotificationWorker",
    "InMemoryNotificationEnvelopeConsumer",
    "RabbitMQHTTPConsumer",
    "build_notification_worker_from_settings",
    "NotificationService",
    "NotificationEventBridge",
]


def __getattr__(name: str):  # pragma: no cover - thin compatibility shim
    if name in {
        "InMemoryNotificationEnvelopeConsumer",
        "NotificationWorker",
        "RabbitMQHTTPConsumer",
        "build_notification_worker_from_settings",
    }:
        from services.notification_service.worker import (
            InMemoryNotificationEnvelopeConsumer,
            NotificationWorker,
            RabbitMQHTTPConsumer,
            build_notification_worker_from_settings,
        )

        mapping = {
            "InMemoryNotificationEnvelopeConsumer": InMemoryNotificationEnvelopeConsumer,
            "NotificationWorker": NotificationWorker,
            "RabbitMQHTTPConsumer": RabbitMQHTTPConsumer,
            "build_notification_worker_from_settings": build_notification_worker_from_settings,
        }
        return mapping[name]
    raise AttributeError(name)
