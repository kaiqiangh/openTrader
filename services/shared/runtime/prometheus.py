from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Mapping

_DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


@dataclass(slots=True)
class _CounterMetric:
    name: str
    help_text: str
    label_names: tuple[str, ...]
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)


@dataclass(slots=True)
class _HistogramSample:
    bucket_counts: list[int]
    count: int = 0
    total_sum: float = 0.0


@dataclass(slots=True)
class _HistogramMetric:
    name: str
    help_text: str
    label_names: tuple[str, ...]
    buckets: tuple[float, ...]
    values: dict[tuple[tuple[str, str], ...], _HistogramSample] = field(default_factory=dict)


class PrometheusRegistry:
    """Minimal Prometheus text exposition registry for counters and histograms."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, _CounterMetric] = {}
        self._histograms: dict[str, _HistogramMetric] = {}

    def inc_counter(
        self,
        *,
        name: str,
        help_text: str,
        label_values: Mapping[str, str] | None = None,
        amount: float = 1.0,
    ) -> None:
        normalized = _normalize_labels(label_values)
        with self._lock:
            metric = self._counters.get(name)
            if metric is None:
                metric = _CounterMetric(
                    name=name,
                    help_text=help_text,
                    label_names=tuple(label for label, _ in normalized),
                )
                self._counters[name] = metric
            metric.values[normalized] = metric.values.get(normalized, 0.0) + float(amount)

    def observe_histogram(
        self,
        *,
        name: str,
        help_text: str,
        value: float,
        label_values: Mapping[str, str] | None = None,
        buckets: tuple[float, ...] = _DEFAULT_BUCKETS,
    ) -> None:
        normalized = _normalize_labels(label_values)
        ordered_buckets = tuple(sorted(float(item) for item in buckets))
        with self._lock:
            metric = self._histograms.get(name)
            if metric is None:
                metric = _HistogramMetric(
                    name=name,
                    help_text=help_text,
                    label_names=tuple(label for label, _ in normalized),
                    buckets=ordered_buckets,
                )
                self._histograms[name] = metric
            sample = metric.values.get(normalized)
            if sample is None:
                sample = _HistogramSample(bucket_counts=[0 for _ in metric.buckets])
                metric.values[normalized] = sample

            observed = float(value)
            sample.count += 1
            sample.total_sum += observed
            for index, bucket in enumerate(metric.buckets):
                if observed <= bucket:
                    sample.bucket_counts[index] += 1

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            for metric in sorted(self._counters.values(), key=lambda item: item.name):
                lines.append(f"# HELP {metric.name} {metric.help_text}")
                lines.append(f"# TYPE {metric.name} counter")
                for labels, value in sorted(metric.values.items()):
                    lines.append(f"{metric.name}{_labels_expr(labels)} {value}")

            for metric in sorted(self._histograms.values(), key=lambda item: item.name):
                lines.append(f"# HELP {metric.name} {metric.help_text}")
                lines.append(f"# TYPE {metric.name} histogram")
                for labels, sample in sorted(metric.values.items()):
                    for index, bucket in enumerate(metric.buckets):
                        bucket_labels = (*labels, ("le", _format_bucket(bucket)))
                        lines.append(
                            f"{metric.name}_bucket{_labels_expr(bucket_labels)} {sample.bucket_counts[index]}"
                        )
                    inf_labels = (*labels, ("le", "+Inf"))
                    lines.append(f"{metric.name}_bucket{_labels_expr(inf_labels)} {sample.count}")
                    lines.append(f"{metric.name}_sum{_labels_expr(labels)} {sample.total_sum}")
                    lines.append(f"{metric.name}_count{_labels_expr(labels)} {sample.count}")
        return "\n".join(lines) + ("\n" if lines else "")


def _normalize_labels(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    normalized = ((str(key), str(value)) for key, value in labels.items())
    return tuple(sorted(normalized, key=lambda item: item[0]))


def _labels_expr(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    fragments = [f'{key}="{_escape_label_value(value)}"' for key, value in labels]
    return "{" + ",".join(fragments) + "}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_bucket(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"

