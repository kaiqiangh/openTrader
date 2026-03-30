"""Shared utility functions for runtime workers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import hashlib
import httpx
import os
import xml.etree.ElementTree as ET
from urllib.parse import urlparse


_NEWS_SOURCE_ITEM_ID_MAX_LEN = 128


# ── Time helpers ──────────────────────────────────────────────────────────────

def _utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── Value coercion ────────────────────────────────────────────────────────────

def _to_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _parse_csv_tokens(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    return tuple(token.strip() for token in raw.split(",") if token.strip())


def _maybe_uuid(value: Any) -> str | None:
    import uuid

    raw = str(value).strip() if value is not None else ""
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        return None


def _resolve_requested_quantity(raw_quantity: float | None) -> Decimal:
    """Resolve and validate requested_quantity from raw payload value.

    Raises ValueError if quantity is zero, negative, or missing.
    Returns absolute value (always positive).
    """
    from decimal import Decimal

    if raw_quantity is None:
        raise ValueError("requested_quantity must be positive (got None)")
    quantity = abs(Decimal(str(raw_quantity)))
    if quantity <= 0:
        raise ValueError(f"requested_quantity must be positive (got {raw_quantity})")
    return quantity


# ── Mapping / collection safety ───────────────────────────────────────────────

def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _safe_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return list(value)


# ── Worker observability ──────────────────────────────────────────────────────

def _worker_activity_snapshot(worker: Any) -> dict[str, Any]:
    snapshot_fn = getattr(worker, "activity_snapshot", None)
    if snapshot_fn is None or not callable(snapshot_fn):
        return {}
    try:
        payload = snapshot_fn()
    except Exception:  # noqa: BLE001 - observability helper must never crash the worker loop
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


def _correlation_from_activity(activity: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(activity, Mapping):
        return {}
    return {
        "trace_id": _find_nested_activity_value(activity, "trace_id"),
        "decision_id": _find_nested_activity_value(activity, "decision_id"),
        "order_id": _find_nested_activity_value(activity, "order_id"),
        "strategy_id": _find_nested_activity_value(activity, "strategy_id"),
        "mode": _find_nested_activity_value(activity, "mode"),
    }


def _find_nested_activity_value(payload: Any, key: str, *, depth: int = 0) -> str | None:
    if depth > 3:
        return None
    if isinstance(payload, Mapping):
        direct = payload.get(key)
        if direct is not None:
            text_value = str(direct).strip()
            if text_value:
                return text_value
        for value in payload.values():
            nested = _find_nested_activity_value(value, key, depth=depth + 1)
            if nested is not None:
                return nested
        return None
    if isinstance(payload, list):
        for item in payload[:5]:
            nested = _find_nested_activity_value(item, key, depth=depth + 1)
            if nested is not None:
                return nested
    return None


# ── Market helpers ────────────────────────────────────────────────────────────

def _normalize_market_fetch_mode(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"rest", "restful", "http"}:
        return "rest"
    if normalized in {"websocket", "ws"}:
        return "websocket"
    raise ValueError("MARKET_DATA_FETCH_MODE must be 'rest' or 'websocket'")


def _resolve_market_exchanges() -> tuple[str, ...]:
    configured = _parse_csv_tokens(os.getenv("MARKET_EXCHANGES"))
    if not configured:
        fallback = os.getenv("EXCHANGE_DEFAULT", "binance").strip().lower()
        configured = (fallback,) if fallback else ("binance",)
    normalized = tuple(value.lower() for value in configured)
    invalid = tuple(value for value in normalized if value not in {"binance", "bitget"})
    if invalid:
        raise ValueError("MARKET_EXCHANGES entries must be binance or bitget")
    return normalized


def _resolve_market_symbols(*, default_symbol: str) -> tuple[str, ...]:
    configured = _parse_csv_tokens(os.getenv("MARKET_SYMBOLS"))
    if not configured:
        fallback = default_symbol.strip().upper()
        return (fallback,) if fallback else ("BTC/USDT",)
    return tuple(value.upper() for value in configured)


# ── News helpers ──────────────────────────────────────────────────────────────

def _resolve_news_source_mode(*, require_database: bool) -> str:
    configured = os.getenv("NEWS_SOURCE_MODE", "").strip().lower()
    if configured and configured not in {"real", "mock"}:
        raise ValueError("NEWS_SOURCE_MODE must be 'real' or 'mock'")
    if require_database:
        return "real"
    return configured or "mock"


def _default_news_rss_feeds() -> tuple[str, ...]:
    return (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    )


def _http_get_text(url: str, *, timeout_seconds: float) -> str:
    with httpx.Client(timeout=timeout_seconds, verify=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _parse_rss_items(*, feed_url: str, rss_xml: str, limit: int) -> list[dict[str, Any]]:
    root = ET.fromstring(rss_xml)
    items: list[dict[str, Any]] = []
    source = _infer_source_name(feed_url)

    for item in root.findall(".//item"):
        title = _first_child_text(item, ("title",))
        link = _first_child_text(item, ("link",))
        published_at = _first_child_text(item, ("pubDate", "published")) or _utc_now_iso()
        description = _first_child_text(item, ("description", "summary"))
        if not title or not link:
            continue
        items.append(
            {
                "source": source,
                "source_item_id": _build_source_item_id(source=source, link=link),
                "title": title,
                "url": link,
                "published_at": published_at,
                "content": description,
                "metadata": {"language": "en"},
            }
        )
        if len(items) >= limit:
            return items

    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        if len(items) >= limit:
            break
        title = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}title",))
        updated = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}updated",))
        content = _first_child_text(entry, ("{http://www.w3.org/2005/Atom}summary",))
        link = ""
        for link_node in entry.findall("{http://www.w3.org/2005/Atom}link"):
            href = str(link_node.attrib.get("href", "")).strip()
            if href:
                link = href
                break
        if not title or not link:
            continue
        items.append(
            {
                "source": source,
                "source_item_id": _build_source_item_id(source=source, link=link),
                "title": title,
                "url": link,
                "published_at": updated or _utc_now_iso(),
                "content": content,
                "metadata": {"language": "en"},
            }
        )
    return items


def _first_child_text(element: ET.Element, tags: tuple[str, ...]) -> str:
    for tag in tags:
        child = element.find(tag)
        if child is not None and child.text is not None and child.text.strip():
            return child.text.strip()
    return ""


def _infer_source_name(feed_url: str) -> str:
    parsed = urlparse(feed_url)
    hostname = (parsed.hostname or "unknown").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname or "unknown"


def _build_source_item_id(*, source: str, link: str) -> str:
    source_key = (source or "unknown").strip().lower()
    candidate = f"{source_key}:{link.strip()}"
    if len(candidate) <= _NEWS_SOURCE_ITEM_ID_MAX_LEN:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    bounded_source = source_key[:63] if source_key else "unknown"
    return f"{bounded_source}:{digest}"
