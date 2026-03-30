from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from services.api import app as api_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(*, strict_database_mode: bool) -> APISettings:
    return make_test_settings(read_only_mode=False, strict_database_mode=strict_database_mode)


class _BrokenRepository:
    def load_state(self, *, default_mode: str):  # pragma: no cover - exercised via API paths
        raise RuntimeError(f"db unavailable for mode {default_mode}")


class _KlineQueryFailRepository:
    def load_state(self, *, default_mode: str):
        return build_default_state(default_mode=default_mode)

    def list_market_klines(self, **_: object):
        raise RuntimeError("query timeout")


def test_create_app_fails_fast_when_repository_bootstrap_fails_in_strict_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise() -> object:
        raise RuntimeError("cannot connect")

    monkeypatch.setattr(api_app, "_build_repository_from_env", _raise)

    with pytest.raises(RuntimeError, match="failed to initialize control-plane repository"):
        api_app.create_app(settings=_settings(strict_database_mode=True))


def test_create_app_falls_back_to_default_state_when_strict_mode_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise() -> object:
        raise RuntimeError("cannot connect")

    monkeypatch.setattr(api_app, "_build_repository_from_env", _raise)

    settings = _settings(strict_database_mode=False)
    app = api_app.create_app(settings=settings)
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)
    payload = client.get(
        "/health/readiness", headers={"Authorization": f"Bearer {viewer_token}"}
    ).json()
    assert payload["status"] == "ready"
    assert payload["mode"] == "MOCK"


def test_health_readiness_returns_503_when_repository_refresh_fails_in_strict_mode() -> None:
    settings = _settings(strict_database_mode=True)
    app = api_app.create_app(
        settings=settings,
        state=build_default_state(default_mode=settings.default_mode),
        repository=_BrokenRepository(),
    )
    client = TestClient(app)

    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)
    response = client.get("/health/readiness", headers={"Authorization": f"Bearer {viewer_token}"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Control-plane repository unavailable"


def test_ops_market_klines_returns_503_when_repository_query_fails() -> None:
    settings = _settings(strict_database_mode=True)
    viewer = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)
    app = api_app.create_app(
        settings=settings,
        state=build_default_state(default_mode=settings.default_mode),
        repository=_KlineQueryFailRepository(),
    )
    client = TestClient(app)

    response = client.get(
        "/ops/market/klines",
        headers=_auth_headers(viewer),
        params={"symbol": "BTC/USDT", "interval": "1m", "limit": 10},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "market data repository unavailable"
