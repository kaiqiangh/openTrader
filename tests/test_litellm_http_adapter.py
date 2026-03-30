from __future__ import annotations

from typing import Any
import json

import httpx
import pytest

from services.llm_gateway.openai_compatible_adapter import LLMProviderError, OpenAICompatibleClient


class _FakeHTTPResponse:
    def __init__(self, payload: Any) -> None:
        self.text = json.dumps(payload)
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    def __init__(self, timeout, verify, response: _FakeHTTPResponse, captured: dict[str, Any]) -> None:
        self._response = response
        self._captured = captured
        self._timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> _FakeHTTPResponse:
        self._captured["url"] = url
        self._captured["timeout"] = self._timeout
        self._captured["authorization"] = headers.get("Authorization")
        self._captured["body"] = json.loads(content.decode("utf-8"))
        return self._response


def _make_fake_client_cls(response, captured):
    class _FakeClientCls:
        def __init__(self, **kwargs):
            self._inner = _FakeClient(kwargs.get("timeout"), kwargs.get("verify"), response, captured)

        def __enter__(self):
            return self._inner

        def __exit__(self, exc_type, exc, tb):
            return False
    return _FakeClientCls


@pytest.mark.asyncio
async def test_litellm_http_adapter_posts_json_and_returns_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    response = _FakeHTTPResponse(
        {
            "choices": [
                {
                    "message": {
                        "content": "hello",
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )

    monkeypatch.setattr(httpx, "Client", _make_fake_client_cls(response, captured))

    client = OpenAICompatibleClient(
        base_url="http://litellm:4000",
        api_key="secret-token",
        timeout_seconds=7.5,
    )
    result = await client.complete(
        model="gpt-4o-mini",
        messages=(
            {"role": "system", "content": "be concise"},
            {"role": "user", "content": "hello"},
        ),
        request_kwargs={"temperature": 0.2, "max_tokens": 128},
    )

    assert captured["url"].endswith("/chat/completions")
    assert captured["timeout"] == 7.5
    assert captured["authorization"] == "Bearer secret-token"
    assert captured["body"]["model"] == "gpt-4o-mini"
    assert result["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_litellm_http_adapter_raises_on_error_payload(monkeypatch) -> None:
    response = _FakeHTTPResponse({"error": {"message": "provider failed"}})

    monkeypatch.setattr(httpx, "Client", _make_fake_client_cls(response, {}))

    client = OpenAICompatibleClient(base_url="http://litellm:4000")
    with pytest.raises(LLMProviderError):
        await client.complete(
            model="gpt-4o-mini",
            messages=({"role": "user", "content": "hello"},),
            request_kwargs={},
        )


def test_litellm_http_adapter_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleClient(base_url="http://litellm:4000", timeout_seconds=0.0)


def test_litellm_http_adapter_rejects_empty_endpoint_path() -> None:
    with pytest.raises(ValueError):
        OpenAICompatibleClient(base_url="http://litellm:4000", endpoint_path="  ")
