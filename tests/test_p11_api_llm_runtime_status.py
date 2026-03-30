from __future__ import annotations


from fastapi.testclient import TestClient

from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings() -> APISettings:
    return make_test_settings(
        llm_runtime_enabled=True,
        litellm_base_url="http://litellm:4000",
        llm_quick_provider_order=("openai", "anthropic"),
        llm_deep_provider_order=("anthropic", "openai"),
    )


def test_llm_runtime_status_endpoint_reflects_runtime_settings() -> None:
    settings = _settings()
    app = create_app(
        settings=settings, state=build_default_state(default_mode=settings.default_mode)
    )
    client = TestClient(app)
    token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    response = client.get("/ops/llm/runtime", headers=_auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime_enabled"] is True
    assert payload["litellm_base_url_configured"] is True
    assert payload["quick_provider_order"] == ["openai", "anthropic"]
    assert payload["deep_provider_order"] == ["anthropic", "openai"]
    assert payload["total_calls"] >= 0
    assert payload["succeeded_calls"] >= 0
    assert payload["failed_calls"] >= 0
