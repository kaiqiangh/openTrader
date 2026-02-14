from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import random


@dataclass(frozen=True, slots=True)
class BackoffConfig:
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    jitter_ratio: float = 0.2
    stale_after_seconds: float = 15.0


class ConnectionResilienceManager:
    def __init__(
        self,
        *,
        config: BackoffConfig | None = None,
        random_fn: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or BackoffConfig()
        self._random_fn = random_fn or random.random
        self._last_heartbeat_seconds: float | None = None
        self._disconnect_attempts = 0

    def mark_heartbeat(self, *, now_seconds: float) -> None:
        self._last_heartbeat_seconds = now_seconds

    def is_stale(self, *, now_seconds: float) -> bool:
        if self._last_heartbeat_seconds is None:
            return True
        return (now_seconds - self._last_heartbeat_seconds) > self.config.stale_after_seconds

    def next_backoff_seconds(self, *, attempt: int) -> float:
        if attempt <= 1:
            raw = self.config.base_delay_seconds
        else:
            raw = self.config.base_delay_seconds * (self.config.backoff_multiplier ** (attempt - 1))
        capped = min(raw, self.config.max_delay_seconds)

        jitter_window = capped * self.config.jitter_ratio
        jitter_offset = ((self._random_fn() * 2.0) - 1.0) * jitter_window
        return max(0.0, min(self.config.max_delay_seconds, capped + jitter_offset))

    def record_disconnect(self, *, now_seconds: float) -> float:
        self._disconnect_attempts += 1
        return self.next_backoff_seconds(attempt=self._disconnect_attempts)

    def record_reconnect_success(self, *, now_seconds: float) -> None:
        self._disconnect_attempts = 0
        self.mark_heartbeat(now_seconds=now_seconds)
