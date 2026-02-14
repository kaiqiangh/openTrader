from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

_DEFAULT_CORRELATION_KEYS = (
    "trace_id",
    "decision_id",
    "order_id",
    "strategy_id",
    "mode",
)


@dataclass(slots=True)
class StructuredLogger:
    """Small JSON logger utility with stable correlation-key schema."""

    service: str
    sink: Callable[[str], None] = print

    def debug(self, *, event: str, **kwargs: Any) -> dict[str, Any]:
        return self._emit(level="DEBUG", event=event, **kwargs)

    def info(self, *, event: str, **kwargs: Any) -> dict[str, Any]:
        return self._emit(level="INFO", event=event, **kwargs)

    def warning(self, *, event: str, **kwargs: Any) -> dict[str, Any]:
        return self._emit(level="WARNING", event=event, **kwargs)

    def error(self, *, event: str, **kwargs: Any) -> dict[str, Any]:
        return self._emit(level="ERROR", event=event, **kwargs)

    def _emit(
        self,
        *,
        level: str,
        event: str,
        context: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "timestamp": _utc_now_iso(),
            "level": level,
            "service": self.service,
            "event": event,
        }
        for key in _DEFAULT_CORRELATION_KEYS:
            payload[key] = kwargs.pop(key, None)
        if context:
            payload["context"] = dict(context)
        if kwargs:
            payload["context"] = {**payload.get("context", {}), **kwargs}

        self.sink(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

