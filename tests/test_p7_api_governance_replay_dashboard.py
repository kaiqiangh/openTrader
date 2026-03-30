from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from services.agent_orchestrator.memory_layer import DecisionMemoryRecord
from services.agent_orchestrator.replay_service import AgentMessageRecord, AgentRunRecord, DecisionTraceRecord
from services.api.app import create_app
from services.api.settings import APISettings
from services.api.state import build_default_state
from services.llm_gateway.persistence import LLMCallRecord
from tests.jwt_test_helpers import encode_jwt_rs256, make_test_settings

def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def _settings() -> APISettings:
    return make_test_settings()

def _seed_replay_data(state) -> str:
    decision_id = "438f7b8d-9725-4af6-b57d-7a88221e22f3"
    trace_id = "eb1e2b6d-5a10-4534-95fc-5e61e53eb0a9"
    state.replay_traces[decision_id] = DecisionTraceRecord(
        decision_id=decision_id,
        trace_id=trace_id,
        strategy_id="btc-momentum",
        mode="MOCK",
        status="RISK_APPROVED",
        started_at="2026-02-14T19:00:00Z",
        completed_at="2026-02-14T19:00:02Z",
    )
    state.replay_agent_runs[decision_id] = [
        AgentRunRecord(
            agent_run_id="run-1",
            decision_id=decision_id,
            agent_name="planner",
            input_ref="mem:context",
            output_ref="mem:plan",
            latency_ms=8.5,
            status="SUCCEEDED",
            started_at="2026-02-14T19:00:00.1Z",
            completed_at="2026-02-14T19:00:00.2Z",
        )
    ]
    state.replay_agent_messages["run-1"] = [
        AgentMessageRecord(
            message_id="msg-1",
            agent_run_id="run-1",
            role="assistant",
            payload_json={"action": "BUY"},
            created_at="2026-02-14T19:00:00.2Z",
        )
    ]
    state.replay_llm_calls[decision_id] = [
        LLMCallRecord(
            llm_call_id="call-1",
            trace_id=trace_id,
            decision_id=decision_id,
            strategy_id="btc-momentum",
            agent_name="planner",
            provider="litellm",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "user", "content": "plan"}]},
            response_payload={"status": "succeeded", "content": "buy"},
            prompt_tokens=20,
            completion_tokens=10,
            total_tokens=30,
            latency_ms=25.0,
            estimated_cost=0.001,
            created_at="2026-02-14T19:00:00.2Z",
        )
    ]
    state.replay_summaries[decision_id] = DecisionMemoryRecord(
        trace_id=trace_id,
        decision_id=decision_id,
        strategy_id="btc-momentum",
        mode="MOCK",
        status="RISK_APPROVED",
        summary={"plan": {"action": "BUY"}},
        lifecycle=({"event_type": "agent.decision.intent_published"},),
        persisted_at="2026-02-14T19:00:02Z",
    )
    return decision_id

def test_governance_usage_and_breach_history_endpoints() -> None:
    settings = _settings()
    state = build_default_state(default_mode=settings.default_mode)
    state.llm_quota_limits[("btc-momentum", "planner")] = {
        "daily_token_limit": 1000,
        "monthly_cost_limit": 5.0,
        "is_hard_limit": True,
        "updated_at": "2026-02-14T18:00:00Z",
    }
    state.llm_call_records.append(
        LLMCallRecord(
            llm_call_id="call-usage-1",
            trace_id="8e847a45-98ec-4064-bce8-e2a70c4c3127",
            decision_id="046f5dd6-e7b5-4cc4-92b2-318a53de50f4",
            strategy_id="btc-momentum",
            agent_name="planner",
            provider="litellm",
            model="gpt-4o-mini",
            prompt_payload={"messages": [{"role": "user", "content": "hello"}]},
            response_payload={"status": "succeeded"},
            prompt_tokens=40,
            completion_tokens=20,
            total_tokens=60,
            latency_ms=40.0,
            estimated_cost=0.2,
            created_at="2026-02-14T18:10:00Z",
        )
    )
    state.llm_call_records.append(
        LLMCallRecord(
            llm_call_id="call-breach-1",
            trace_id="95b5bff5-0fd5-4d0b-90e8-40038f4b3242",
            decision_id="d11ef6a5-38f9-4cdf-b22e-28a84c61dcc7",
            strategy_id="btc-momentum",
            agent_name="planner",
            provider="quota_guard",
            model="quota_guard",
            prompt_payload={"messages": []},
            response_payload={
                "status": "quota_blocked",
                "reason": "monthly_cost_limit_exceeded",
                "projected_tokens": 2400,
                "projected_cost": 5.4,
            },
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            estimated_cost=0.0,
            created_at="2026-02-14T18:12:00Z",
        )
    )

    app = create_app(settings=settings, state=state)
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    usage_response = client.get(
        "/governance/llm/usage",
        headers=_auth_headers(viewer_token),
        params={"strategy_id": "btc-momentum"},
    )
    assert usage_response.status_code == 200
    usage_item = usage_response.json()["items"][0]
    assert usage_item["strategy_id"] == "btc-momentum"
    assert usage_item["agent_name"] == "planner"
    assert usage_item["daily_token_limit"] == 1000
    assert usage_item["breach_count"] == 1

    breaches_response = client.get("/governance/llm/breaches", headers=_auth_headers(viewer_token))
    assert breaches_response.status_code == 200
    breach_item = breaches_response.json()["items"][0]
    assert breach_item["reason"] == "monthly_cost_limit_exceeded"
    assert breach_item["decision_id"] == "d11ef6a5-38f9-4cdf-b22e-28a84c61dcc7"

    calls_response = client.get("/governance/llm/calls", headers=_auth_headers(viewer_token))
    assert calls_response.status_code == 200
    call_items = calls_response.json()["items"]
    assert len(call_items) == 2
    assert call_items[0]["status"] == "quota_blocked"
    assert call_items[1]["status"] == "succeeded"

def test_governance_breaches_can_include_failed_calls() -> None:
    settings = _settings()
    state = build_default_state(default_mode=settings.default_mode)
    state.llm_call_records.append(
        LLMCallRecord(
            llm_call_id="call-failed-1",
            trace_id="d4f5dcab-6263-44ec-b923-1229f6901060",
            decision_id="e5938b40-f2c6-4299-b4fa-56f1cf187dd2",
            strategy_id="btc-momentum",
            agent_name="planner",
            provider="litellm",
            model="deepseek-chat",
            prompt_payload={"messages": [{"role": "user", "content": "test"}]},
            response_payload={"status": "failed", "provider_errors": ["timeout"]},
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=0.0,
            estimated_cost=0.0,
            created_at="2026-02-14T18:15:00Z",
        )
    )

    app = create_app(settings=settings, state=state)
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    response = client.get(
        "/governance/llm/breaches",
        headers=_auth_headers(viewer_token),
        params={"include_failures": "true"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["reason"] == "timeout"
    assert items[0]["decision_id"] == "e5938b40-f2c6-4299-b4fa-56f1cf187dd2"

def test_replay_request_and_retrieval_endpoints() -> None:
    settings = _settings()
    state = build_default_state(default_mode=settings.default_mode)
    decision_id = _seed_replay_data(state)

    app = create_app(settings=settings, state=state)
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    request_response = client.post(
        "/replay/requests",
        headers=_auth_headers(viewer_token),
        json={"decision_id": decision_id},
    )
    assert request_response.status_code == 200
    replay_request = request_response.json()
    assert replay_request["decision_id"] == decision_id
    assert replay_request["status"] == "COMPLETED"
    assert replay_request["result"]["deterministic_digest"]

    request_id = replay_request["request_id"]
    request_detail = client.get(f"/replay/requests/{request_id}", headers=_auth_headers(viewer_token))
    assert request_detail.status_code == 200
    assert request_detail.json()["request_id"] == request_id

    decision_detail = client.get(f"/replay/decisions/{decision_id}", headers=_auth_headers(viewer_token))
    assert decision_detail.status_code == 200
    assert decision_detail.json()["decision_id"] == decision_id
    assert decision_detail.json()["status"] == "RISK_APPROVED"

    catalog_response = client.get("/replay/catalog", headers=_auth_headers(viewer_token))
    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert catalog_payload["decisions"][0]["decision_id"] == decision_id
    assert catalog_payload["requests"][0]["request_id"] == request_id

def test_replay_decision_not_found_returns_404() -> None:
    settings = _settings()
    app = create_app(settings=settings, state=build_default_state(default_mode=settings.default_mode))
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    response = client.get(
        "/replay/decisions/0f09ef0f-6c7a-429f-a3cf-9dbff6a5979f",
        headers=_auth_headers(viewer_token),
    )
    assert response.status_code == 404

def test_dashboard_shell_routes_render_navigation_and_live_sections() -> None:
    settings = _settings()
    state = build_default_state(default_mode=settings.default_mode)
    _seed_replay_data(state)
    app = create_app(settings=settings, state=state)
    client = TestClient(app)
    viewer_token = encode_jwt_rs256(subject="viewer-user", role="viewer", settings=settings)

    dashboard = client.get("/dashboard", headers=_auth_headers(viewer_token))
    status_page = client.get("/dashboard/status", headers=_auth_headers(viewer_token))
    governance_page = client.get("/dashboard/governance", headers=_auth_headers(viewer_token))
    replay_page = client.get("/dashboard/replay", headers=_auth_headers(viewer_token))

    assert dashboard.status_code == 200
    assert "legacy API-served dashboard has been removed" in dashboard.text
    assert "http://localhost:3000/" in dashboard.text
    assert status_page.status_code == 200
    assert "http://localhost:3000/status" in status_page.text
    assert governance_page.status_code == 200
    assert "http://localhost:3000/governance" in governance_page.text
    assert replay_page.status_code == 200
    assert "http://localhost:3000/replay" in replay_page.text
