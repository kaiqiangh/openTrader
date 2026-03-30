"""Synchronous event publisher for use in non-async endpoints.

Thin wrapper around the RabbitMQ HTTP management API that can be called
from synchronous FastAPI handlers without needing an async broker instance.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping
from urllib import parse

import httpx

from services.shared.runtime.rabbitmq_http_broker import _DEFAULT_EXCHANGE_BY_PREFIX

logger = logging.getLogger(__name__)


def _resolve_exchange(routing_key: str) -> str:
    for prefix, exchange_name in _DEFAULT_EXCHANGE_BY_PREFIX.items():
        if routing_key.startswith(prefix):
            return exchange_name
    raise ValueError(f"unable to resolve exchange for routing key '{routing_key}'")


def publish_event(
    event_type: str,
    payload: Mapping[str, Any],
    *,
    api_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    timeout_seconds: float = 2.0,
) -> None:
    """Publish *payload* with routing key *event_type* to RabbitMQ.

    Reads connection details from environment when *api_url*/*username*/*password*
    are not supplied.
    """
    api_url = api_url or os.getenv("RUNTIME_RABBITMQ_HTTP_API_URL", "").strip().rstrip("/")
    username = username or os.getenv("RABBITMQ_DEFAULT_USER", "").strip()
    password = password or os.getenv("RABBITMQ_DEFAULT_PASS", "").strip()

    if not all([api_url, username, password]):
        logger.warning("publish_event_skipped reason=missing_rabbitmq_config routing_key=%s", event_type)
        return

    exchange_name = _resolve_exchange(event_type)
    exchange_ref = parse.quote(exchange_name, safe="")
    url = f"{api_url}/exchanges/%2F/{exchange_ref}/publish"

    body = json.dumps(
        {
            "properties": {"delivery_mode": 2},
            "routing_key": event_type,
            "payload": json.dumps(dict(payload)),
            "payload_encoding": "string",
        }
    ).encode("utf-8")

    auth = httpx.BasicAuth(username=username, password=password)
    try:
        response = httpx.post(url, content=body, auth=auth, timeout=timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("publish_event_failed routing_key=%s", event_type, exc_info=True)
