"""News ingestion source connector framework."""

from services.news_ingestion.source_connectors import (
    CallableSourceConnector,
    ConnectorCycleResult,
    ConnectorFetchResult,
    ConnectorNotFoundError,
    ConnectorRegistrationError,
    NewsSourceConnector,
    NewsSourceConnectorFramework,
    NewsSourceRecord,
    SourceConnectorRegistry,
)

__all__ = [
    "NewsSourceRecord",
    "ConnectorFetchResult",
    "ConnectorCycleResult",
    "NewsSourceConnector",
    "ConnectorRegistrationError",
    "ConnectorNotFoundError",
    "CallableSourceConnector",
    "SourceConnectorRegistry",
    "NewsSourceConnectorFramework",
]
