"""News ingestion source connector framework."""

from services.news_ingestion.ingestion_service import (
    InMemoryNewsItemStore,
    NewsIngestionBatchResult,
    NewsIngestionError,
    NewsIngestionOutcome,
    NewsIngestionService,
    NewsItemStore,
    NormalizedNewsItem,
)
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
from services.news_ingestion.tagging_relevance import (
    InMemoryNewsTagStore,
    NewsTag,
    NewsTaggingRelevancePipeline,
    NewsTagStore,
    TaggingBatchResult,
)

__all__ = [
    "NormalizedNewsItem",
    "NewsIngestionOutcome",
    "NewsIngestionBatchResult",
    "NewsIngestionError",
    "NewsItemStore",
    "InMemoryNewsItemStore",
    "NewsIngestionService",
    "NewsSourceRecord",
    "ConnectorFetchResult",
    "ConnectorCycleResult",
    "NewsSourceConnector",
    "ConnectorRegistrationError",
    "ConnectorNotFoundError",
    "CallableSourceConnector",
    "SourceConnectorRegistry",
    "NewsSourceConnectorFramework",
    "NewsTag",
    "TaggingBatchResult",
    "NewsTagStore",
    "InMemoryNewsTagStore",
    "NewsTaggingRelevancePipeline",
]
