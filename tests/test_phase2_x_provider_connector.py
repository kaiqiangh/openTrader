from __future__ import annotations

from services.news_ingestion.x_provider_connector import XProviderConnector, XProviderConnectorError


def test_x_provider_connector_normalizes_records() -> None:
    def _fake_fetch(url, headers, timeout_seconds):
        _ = url, headers, timeout_seconds
        return {
            "data": [
                {
                    "id": "123",
                    "text": "BTC breaks resistance with strong spot demand",
                    "created_at": "2026-02-19T19:00:00Z",
                    "author_id": "user-1",
                    "lang": "en",
                    "public_metrics": {"retweet_count": 1, "like_count": 2},
                }
            ]
        }

    connector = XProviderConnector(
        api_base_url="https://api.x.com/2/tweets/search/recent",
        bearer_token="test-token",
        query="bitcoin",
        fetch_json_fn=_fake_fetch,
    )

    records = connector.fetch_records(since=None, limit=5)

    assert len(records) == 1
    row = records[0]
    assert row["source"] == "social.x"
    assert row["source_item_id"] == "123"
    assert row["url"] == "https://x.com/i/web/status/123"
    assert row["metadata"]["provider"] == "x"


def test_x_provider_connector_raises_for_error_payload() -> None:
    def _fake_fetch(url, headers, timeout_seconds):
        _ = url, headers, timeout_seconds
        raise XProviderConnectorError("rate limited")

    connector = XProviderConnector(
        api_base_url="https://api.x.com/2/tweets/search/recent",
        bearer_token="test-token",
        query="bitcoin",
        fetch_json_fn=_fake_fetch,
    )

    try:
        connector.fetch_records(since=None, limit=5)
    except XProviderConnectorError as exc:
        assert "rate limited" in str(exc)
    else:
        raise AssertionError("expected XProviderConnectorError")
