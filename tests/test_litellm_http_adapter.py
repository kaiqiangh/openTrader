from __future__ import annotations

from typing import Any
import json

import pytest

from services.llm_gateway.openai_compatible_adapter import LLMProviderError, OpenAICompatibleClient


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        _ = exc_type, exc, tb
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.asyncio
async def test_litellm_http_adapter_posts_json_and_returns_payload(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHTTPResponse(
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

    monkeypatch.setattr("services.llm_gateway.openai_compatible_adapter.urlopen", _fake_urlopen)

    client = OpenAICompatibleClient(
        base_url="http://litellm:4000",
        api_key="secret-token",
        timeout_seconds=7.5,
    )
    response = await client.complete(
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
    assert response["usage"]["total_tokens"] == 15


@pytest.mark.asyncio
async def test_litellm_http_adapter_raises_on_error_payload(monkeypatch) -> None:
    def _fake_urlopen(request, timeout):
        _ = request, timeout
        return _FakeHTTPResponse({"error": {"message": "provider failed"}})

    monkeypatch.setattr("services.llm_gateway.openai_compatible_adapter.urlopen", _fake_urlopen)

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
