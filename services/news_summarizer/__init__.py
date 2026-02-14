"""News summarization service contracts and baseline implementation."""

from services.news_summarizer.summarizer_service import (
    InMemoryNewsSummaryStore,
    NewsSummaryArtifact,
    NewsSummaryStore,
    RollingNewsSummarizer,
)

__all__ = [
    "NewsSummaryArtifact",
    "NewsSummaryStore",
    "InMemoryNewsSummaryStore",
    "RollingNewsSummarizer",
]
