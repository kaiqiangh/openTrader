from __future__ import annotations

from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from services.api.auth import require_viewer
from services.api.models import AuthPrincipal

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_class=HTMLResponse)
def dashboard_home(_: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_shell(
        title="Operations Dashboard",
        heading="Operations Dashboard",
        description="Operator control plane with governance, replay, and mode controls.",
        view="home",
    )


@router.get("/status", response_class=HTMLResponse)
def dashboard_status(_: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_shell(
        title="Live Status",
        heading="Live Status",
        description="Runtime readiness and risk control status.",
        view="status",
    )


@router.get("/governance", response_class=HTMLResponse)
def dashboard_governance(_: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_shell(
        title="LLM Governance",
        heading="LLM Governance",
        description="Token usage, cost utilization, and breach history by strategy and agent.",
        view="governance",
    )


@router.get("/replay", response_class=HTMLResponse)
def dashboard_replay(_: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_shell(
        title="Replay",
        heading="Replay",
        description="Replay requests and prompt/response inspection by decision.",
        view="replay",
    )


@router.get("/mode", response_class=HTMLResponse)
def dashboard_mode(_: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_shell(
        title="Trading Mode Panel",
        heading="Trading Mode Panel",
        description="Current mode, controlled mode switch, and audit-facing change history.",
        view="mode",
    )


@router.get("/news", response_class=HTMLResponse)
def dashboard_news(_: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_shell(
        title="News Intelligence Panel",
        heading="News Intelligence Panel",
        description="News stream, rolling summaries, and symbol impact insights.",
        view="news",
    )


def _render_shell(*, title: str, heading: str, description: str, view: str) -> HTMLResponse:
    nav_cards = [
        ("Dashboard Home", "/dashboard"),
        ("Live Status", "/dashboard/status"),
        ("LLM Governance", "/dashboard/governance"),
        ("Replay Inspector", "/dashboard/replay"),
        ("Mode Panel", "/dashboard/mode"),
        ("News Panel", "/dashboard/news"),
    ]
    nav_html = "".join(
        f"<li><a href='{escape(path)}'>{escape(label)}</a></li>"
        for label, path in nav_cards
    )
    html = (
        "<!doctype html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='utf-8' />"
        "<meta name='viewport' content='width=device-width, initial-scale=1' />"
        f"<title>{escape(title)}</title>"
        "<link rel='stylesheet' href='/static/dashboard.css' />"
        "</head>"
        "<body>"
        "<header class='dashboard-header'>"
        f"<h1>{escape(heading)}</h1>"
        f"<p>{escape(description)}</p>"
        "<nav aria-label='dashboard-navigation'>"
        "<ul class='dashboard-nav'>"
        f"{nav_html}"
        "</ul>"
        "</nav>"
        "</header>"
        f"<main id='dashboard-root' data-view='{escape(view)}' class='dashboard-root'></main>"
        "<noscript>"
        "<p class='noscript-note'>Dashboard interactivity requires JavaScript.</p>"
        "</noscript>"
        "<script type='module' src='/static/dashboard_app.js'></script>"
        "</body>"
        "</html>"
    )
    return HTMLResponse(content=html)
