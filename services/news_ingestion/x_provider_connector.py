from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json


class XProviderConnectorError(RuntimeError):
    """Raised when X provider connector cannot fetch or parse API payload."""


FetchJSONFn = Callable[[str, Mapping[str, str], float], Mapping[str, Any]]


class XProviderConnector:
    """Provider-agnostic social connector implementation for X/Twitter-like APIs."""

    def __init__(
        self,
        *,
        connector_id: str = "social.x",
        api_base_url: str,
        bearer_token: str,
        query: str,
        timeout_seconds: float = 8.0,
        fetch_json_fn: FetchJSONFn | None = None,
    ) -> None:
        normalized_id = connector_id.strip()
        if not normalized_id:
            raise ValueError("connector_id must be non-empty")
        if not api_base_url.strip():
            raise ValueError("api_base_url must be non-empty")
        if not bearer_token.strip():
            raise ValueError("bearer_token must be non-empty")
        if not query.strip():
            raise ValueError("query must be non-empty")

        self.connector_id = normalized_id
        self.api_base_url = api_base_url.rstrip("/")
        self.bearer_token = bearer_token.strip()
        self.query = query.strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self._fetch_json = fetch_json_fn or _default_fetch_json

    def fetch_records(self, *, since: str | None, limit: int) -> tuple[dict[str, Any], ...]:
        if limit <= 0:
            return ()
        params: dict[str, str] = {
            "query": self.query,
            "max_results": str(min(max(10, limit), 100)),
            "tweet.fields": "created_at,lang,author_id,public_metrics",
        }
        if since:
            params["start_time"] = since

        url = f"{self.api_base_url}?{urlencode(params)}"
        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json",
        }
        payload = self._fetch_json(url, headers, self.timeout_seconds)
        rows = payload.get("data")
        if not isinstance(rows, list):
            return ()

        records: list[dict[str, Any]] = []
        for item in rows[:limit]:
            if not isinstance(item, Mapping):
                continue
            text_value = str(item.get("text", "")).strip()
            tweet_id = str(item.get("id", "")).strip()
            if not tweet_id or not text_value:
                continue
            published_at = str(item.get("created_at", "")).strip() or _utc_now_iso()
            author_id = str(item.get("author_id", "")).strip() or "unknown"
            url_value = f"https://x.com/i/web/status/{tweet_id}"
            records.append(
                {
                    "source": self.connector_id,
                    "source_item_id": tweet_id,
                    "published_at": published_at,
                    "title": _short_title(text_value),
                    "url": url_value,
                    "content": text_value,
                    "metadata": {
                        "provider": "x",
                        "author_id": author_id,
                        "language": str(item.get("lang", "en")).strip().lower() or "en",
                        "public_metrics": item.get("public_metrics") if isinstance(item.get("public_metrics"), Mapping) else {},
                    },
                }
            )
        return tuple(records)


def _short_title(text_value: str) -> str:
    value = " ".join(text_value.split())
    if len(value) <= 96:
        return value
    return value[:93].rstrip() + "..."


def _default_fetch_json(url: str, headers: Mapping[str, str], timeout_seconds: float) -> Mapping[str, Any]:
    request = Request(url=url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8") if hasattr(exc, "read") else str(exc)
        raise XProviderConnectorError(f"X provider HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise XProviderConnectorError(f"X provider connection error: {exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise XProviderConnectorError("X provider response is not valid JSON") from exc

    if not isinstance(parsed, Mapping):
        raise XProviderConnectorError("X provider response must be a JSON object")
    errors = parsed.get("errors")
    if isinstance(errors, list) and errors:
        raise XProviderConnectorError(f"X provider returned errors: {errors}")
    return dict(parsed)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
