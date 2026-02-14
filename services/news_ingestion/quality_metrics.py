from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from services.news_ingestion.ingestion_service import NewsIngestionBatchResult


class SummaryLagRecord(Protocol):
    generated_at: str
    window_end: str


@dataclass(slots=True)
class NewsQualityMetrics:
    _connector_cycles_total: int = 0
    _source_fetch_attempts_total: int = 0
    _source_fetch_errors_total: int = 0
    _news_items_inserted_total: int = 0
    _news_items_duplicates_total: int = 0
    _summaries_generated_total: int = 0
    _alerts_total: int = 0
    _latest_published_at_seconds: float | None = None
    _summary_lags_seconds: list[float] = field(default_factory=list)

    def record_connector_cycle(
        self,
        *,
        sources_total: int,
        degraded_sources: tuple[str, ...],
        now_seconds: float,
    ) -> None:
        _ = now_seconds
        source_count = max(0, int(sources_total))
        degraded_count = min(source_count, len(set(degraded_sources)))

        self._connector_cycles_total += 1
        self._source_fetch_attempts_total += source_count
        self._source_fetch_errors_total += degraded_count

    def record_ingestion_batch(self, batch: NewsIngestionBatchResult) -> None:
        self._news_items_inserted_total += max(0, int(batch.inserted_count))
        self._news_items_duplicates_total += max(0, int(batch.duplicate_count))

        for outcome in batch.outcomes:
            if not outcome.inserted or outcome.item is None:
                continue
            published_seconds = _iso_to_unix_seconds(outcome.item.published_at)
            if self._latest_published_at_seconds is None:
                self._latest_published_at_seconds = published_seconds
            else:
                self._latest_published_at_seconds = max(self._latest_published_at_seconds, published_seconds)

    def record_summary_generated(self, summary: SummaryLagRecord) -> None:
        self._summaries_generated_total += 1
        lag_seconds = _iso_to_unix_seconds(summary.generated_at) - _iso_to_unix_seconds(summary.window_end)
        self._summary_lags_seconds.append(max(0.0, lag_seconds))

    def record_alert(self, *, severity: str) -> None:
        _ = severity
        self._alerts_total += 1

    def snapshot(self, *, now_seconds: float) -> dict:
        attempts = self._source_fetch_attempts_total
        errors = self._source_fetch_errors_total
        coverage_ratio = 1.0 if attempts == 0 else max(0.0, min(1.0, 1.0 - (errors / attempts)))
        error_rate = 0.0 if attempts == 0 else max(0.0, min(1.0, errors / attempts))

        freshness = None
        if self._latest_published_at_seconds is not None:
            freshness = max(0.0, now_seconds - self._latest_published_at_seconds)

        lag_avg = None
        lag_latest = None
        lag_max = None
        if self._summary_lags_seconds:
            lag_latest = self._summary_lags_seconds[-1]
            lag_max = max(self._summary_lags_seconds)
            lag_avg = sum(self._summary_lags_seconds) / len(self._summary_lags_seconds)

        return {
            "counters": {
                "connector_cycles_total": self._connector_cycles_total,
                "source_fetch_attempts_total": attempts,
                "source_fetch_errors_total": errors,
                "news_items_inserted_total": self._news_items_inserted_total,
                "news_items_duplicates_total": self._news_items_duplicates_total,
                "summaries_generated_total": self._summaries_generated_total,
                "alerts_total": self._alerts_total,
            },
            "quality": {
                "coverage_ratio": coverage_ratio,
                "error_rate": error_rate,
                "freshness_seconds_latest": freshness,
                "summarization_lag_seconds_avg": lag_avg,
                "summarization_lag_seconds_latest": lag_latest,
                "summarization_lag_seconds_max": lag_max,
            },
        }


def _iso_to_unix_seconds(value: str) -> float:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return parsed.timestamp()
