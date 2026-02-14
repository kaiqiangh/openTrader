from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass(slots=True)
class MarketPipelineMetrics:
    _delta_timestamps: list[float] = field(default_factory=list)
    _delta_lags_ms: list[float] = field(default_factory=list)
    _reconnect_timestamps: list[float] = field(default_factory=list)
    _resync_timestamps: list[float] = field(default_factory=list)

    def record_delta_processed(self, *, lag_ms: float, now_seconds: float) -> None:
        self._delta_timestamps.append(now_seconds)
        self._delta_lags_ms.append(float(lag_ms))

    def record_reconnect(self, *, now_seconds: float) -> None:
        self._reconnect_timestamps.append(now_seconds)

    def record_resync_request(self, *, now_seconds: float) -> None:
        self._resync_timestamps.append(now_seconds)

    def events_per_second(self, *, window_seconds: float, now_seconds: float) -> float:
        if window_seconds <= 0:
            return 0.0
        cutoff = now_seconds - window_seconds
        in_window = [ts for ts in self._delta_timestamps if ts >= cutoff]
        return len(in_window) / window_seconds

    def snapshot(self, *, now_seconds: float) -> dict:
        latest_lag = self._delta_lags_ms[-1] if self._delta_lags_ms else None
        max_lag = max(self._delta_lags_ms) if self._delta_lags_ms else None
        avg_lag = mean(self._delta_lags_ms) if self._delta_lags_ms else None

        return {
            "counters": {
                "deltas_processed_total": len(self._delta_timestamps),
                "reconnects_total": len(self._reconnect_timestamps),
                "resync_requests_total": len(self._resync_timestamps),
            },
            "lag_ms": {
                "latest": latest_lag,
                "avg": avg_lag,
                "max": max_lag,
            },
            "rates": {
                "events_per_second_60s": self.events_per_second(
                    window_seconds=60.0,
                    now_seconds=now_seconds,
                )
            },
        }
