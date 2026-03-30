from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin
import httpx
import asyncio
import json


class LLMProviderError(RuntimeError):
    """Raised when LLM provider HTTP endpoint returns a terminal error."""


class OpenAICompatibleClient:
    """Generic OpenAI-compatible LLM HTTP client (DeepSeek, OpenAI, etc.)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
        endpoint_path: str = "/chat/completions",
    ) -> None:
        if not base_url:
            raise ValueError("base_url must be non-empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        normalized_endpoint = endpoint_path.strip().lstrip("/")
        if not normalized_endpoint:
            raise ValueError("endpoint_path must be non-empty")

        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.endpoint_path = normalized_endpoint

    async def complete(
        self,
        *,
        model: str,
        messages: tuple[Mapping[str, Any], ...],
        request_kwargs: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        payload = {
            "model": model,
            "messages": [dict(item) for item in messages],
        }
        payload.update(dict(request_kwargs))
        return await asyncio.to_thread(self._post_json, payload)

    def _post_json(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        url = urljoin(self.base_url, self.endpoint_path)
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            with httpx.Client(timeout=self.timeout_seconds, verify=True) as client:
                response = client.post(url, content=body, headers=headers)
                response.raise_for_status()
                raw = response.text
        except (
            httpx.HTTPStatusError
        ) as exc:  # pragma: no cover - exercised through monkeypatch tests
            detail = exc.response.text
            raise LLMProviderError(
                f"LLM provider HTTP {exc.response.status_code}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - exercised through monkeypatch tests
            raise LLMProviderError(f"LLM provider connection error: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("LLM provider response is not valid JSON") from exc

        if not isinstance(parsed, Mapping):
            raise LLMProviderError("LLM provider response must be a JSON object")
        if "error" in parsed:
            raise LLMProviderError(f"LLM provider returned error payload: {parsed['error']}")
        return parsed
