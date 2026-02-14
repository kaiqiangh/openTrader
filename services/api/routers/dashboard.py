from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from services.api.auth import require_viewer
from services.api.dependencies import get_control_plane_state
from services.api.models import AuthPrincipal
from services.api.state import ControlPlaneState

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_class=HTMLResponse)
def dashboard_home(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> HTMLResponse:
    cards = [
        ("Live Status", "/dashboard/status", f"Mode: {state.mode}"),
        ("LLM Governance", "/dashboard/governance", "Usage, quotas, and breaches"),
        ("Replay", "/dashboard/replay", "Decision replay requests and trace links"),
    ]
    links = "".join(
        f"<li><a href='{escape(path)}'>{escape(title)}</a><p>{escape(description)}</p></li>"
        for title, path, description in cards
    )
    html = (
        "<html><head><title>Operations Dashboard</title></head><body>"
        "<h1>Operations Dashboard</h1>"
        "<p>FastAPI control-plane shell for operators.</p>"
        "<ul>"
        f"{links}"
        "</ul>"
        "</body></html>"
    )
    return HTMLResponse(content=html)


@router.get("/status", response_class=HTMLResponse)
def dashboard_status(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> HTMLResponse:
    risk_status, _ = state.risk_status()
    html = (
        "<html><head><title>Live Status</title></head><body>"
        "<h1>Live Status</h1>"
        f"<p>Mode: {escape(state.mode)}</p>"
        f"<p>Strategies: {len(state.strategies)}</p>"
        f"<p>Kill switch: {bool(risk_status['kill_switch_enabled'])}</p>"
        f"<p>Circuit breaker open: {bool(risk_status['circuit_breaker_open'])}</p>"
        "<p><a href='/dashboard'>Back to dashboard</a></p>"
        "</body></html>"
    )
    return HTMLResponse(content=html)


@router.get("/governance", response_class=HTMLResponse)
def dashboard_governance(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> HTMLResponse:
    usage_rows = state.list_llm_usage()
    breaches = state.list_llm_breaches(limit=20)
    table_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(item.strategy_id)}</td>"
            f"<td>{escape(item.agent_name)}</td>"
            f"<td>{item.daily_tokens}</td>"
            f"<td>{item.monthly_cost:.6f}</td>"
            f"<td>{item.breach_count}</td>"
            "</tr>"
        )
        for item in usage_rows
    )
    html = (
        "<html><head><title>LLM Governance</title></head><body>"
        "<h1>LLM Governance</h1>"
        f"<p>Usage rows: {len(usage_rows)}</p>"
        f"<p>Recent breaches: {len(breaches)}</p>"
        "<table border='1'><thead>"
        "<tr><th>Strategy</th><th>Agent</th><th>Daily Tokens</th><th>Monthly Cost</th><th>Breaches</th></tr>"
        "</thead><tbody>"
        f"{table_rows}"
        "</tbody></table>"
        "<p><a href='/dashboard'>Back to dashboard</a></p>"
        "</body></html>"
    )
    return HTMLResponse(content=html)


@router.get("/replay", response_class=HTMLResponse)
def dashboard_replay(
    _: AuthPrincipal = Depends(require_viewer),
    state: ControlPlaneState = Depends(get_control_plane_state),
) -> HTMLResponse:
    traces = state.list_replay_traces()
    trace_rows = "".join(
        (
            "<li>"
            f"{escape(item.decision_id)} ({escape(item.status)}) - "
            f"<a href='/replay/decisions/{escape(item.decision_id)}'>JSON</a>"
            "</li>"
        )
        for item in traces
    )
    html = (
        "<html><head><title>Replay</title></head><body>"
        "<h1>Replay</h1>"
        f"<p>Available traces: {len(traces)}</p>"
        "<ul>"
        f"{trace_rows}"
        "</ul>"
        "<p><a href='/dashboard'>Back to dashboard</a></p>"
        "</body></html>"
    )
    return HTMLResponse(content=html)
