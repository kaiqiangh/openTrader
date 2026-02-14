"""News summarization service contracts and baseline implementation."""

from services.news_summarizer.context_injection_bridge import (
    ContextEnvelopePublisher,
    NewsContextInjectionBridge,
)
from services.news_summarizer.resilience import (
    AlertPublisher,
    NewsResilienceAlert,
    NewsResilienceDecision,
    NewsResiliencePolicy,
)
from services.news_summarizer.summarizer_service import (
    InMemoryNewsSummaryStore,
    NewsSummaryArtifact,
    NewsSummaryStore,
    RollingNewsSummarizer,
)

__all__ = [
    "ContextEnvelopePublisher",
    "NewsContextInjectionBridge",
    "AlertPublisher",
    "NewsResilienceAlert",
    "NewsResilienceDecision",
    "NewsResiliencePolicy",
    "NewsSummaryArtifact",
    "NewsSummaryStore",
    "InMemoryNewsSummaryStore",
    "RollingNewsSummarizer",
]
