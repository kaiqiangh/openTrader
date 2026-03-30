from __future__ import annotations

from dataclasses import dataclass
import re
import secrets

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str
    parent_span_id: str | None
    span_id: str
    sampled: bool

    @property
    def traceparent(self) -> str:
        flags = "01" if self.sampled else "00"
        return f"00-{self.trace_id}-{self.span_id}-{flags}"


def generate_trace_id() -> str:
    return secrets.token_hex(16)


def generate_span_id() -> str:
    return secrets.token_hex(8)


def build_traceparent(
    *, trace_id: str | None = None, span_id: str | None = None, sampled: bool = True
) -> str:
    resolved_trace_id = trace_id or generate_trace_id()
    resolved_span_id = span_id or generate_span_id()
    flags = "01" if sampled else "00"
    return f"00-{resolved_trace_id}-{resolved_span_id}-{flags}"


def parse_traceparent(value: str | None) -> TraceContext | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    match = _TRACEPARENT_RE.fullmatch(normalized)
    if match is None:
        return None
    trace_id = match.group(1)
    parent_span = match.group(2)
    flags = match.group(3)
    return TraceContext(
        trace_id=trace_id,
        parent_span_id=parent_span,
        span_id=generate_span_id(),
        sampled=flags != "00",
    )


def resolve_trace_context(incoming_traceparent: str | None) -> TraceContext:
    parsed = parse_traceparent(incoming_traceparent)
    if parsed is not None:
        return parsed
    return TraceContext(
        trace_id=generate_trace_id(),
        parent_span_id=None,
        span_id=generate_span_id(),
        sampled=True,
    )
