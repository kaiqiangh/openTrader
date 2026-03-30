from __future__ import annotations

import os
from html import escape

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from services.api.auth import require_viewer
from services.api.models import AuthPrincipal

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_class=HTMLResponse)
def dashboard_home(_principal: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_notice(
        title="Operations Dashboard",
        route="/",
    )


@router.get("/status", response_class=HTMLResponse)
def dashboard_status(_principal: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_notice(
        title="Live Status",
        route="/status",
    )


@router.get("/governance", response_class=HTMLResponse)
def dashboard_governance(_principal: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_notice(
        title="LLM Governance",
        route="/governance",
    )


@router.get("/replay", response_class=HTMLResponse)
def dashboard_replay(_principal: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_notice(
        title="Replay",
        route="/replay",
    )


@router.get("/mode", response_class=HTMLResponse)
def dashboard_mode(_principal: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_notice(
        title="Trading Mode Panel",
        route="/mode",
    )


@router.get("/news", response_class=HTMLResponse)
def dashboard_news(_principal: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_notice(
        title="News Intelligence Panel",
        route="/news",
    )


@router.get("/notifications", response_class=HTMLResponse)
def dashboard_notifications(_principal: AuthPrincipal = Depends(require_viewer)) -> HTMLResponse:
    return _render_notice(
        title="Notification Observability",
        route="/notifications",
    )


def _render_notice(*, title: str, route: str) -> HTMLResponse:
    dashboard_base = os.getenv("NEXT_DASHBOARD_URL", "http://localhost:3000").rstrip("/")
    target = f"{dashboard_base}{route}"
    html = (
        "<!doctype html>"
        "<html lang='en'>"
        "<head>"
        "<meta charset='utf-8' />"
        "<meta name='viewport' content='width=device-width, initial-scale=1' />"
        f"<title>{escape(title)}</title>"
        "<style>"
        "body{margin:0;background:#08111b;color:#dbe8ff;font-family:'Space Grotesk',sans-serif;}"
        ".card{max-width:720px;margin:9vh auto;padding:24px;border-radius:16px;border:1px solid #1e3349;background:#0f1d2c;box-shadow:0 20px 50px rgba(0,0,0,.35);}"
        "h1{margin:0 0 8px 0;font-size:1.4rem}"
        "p{margin:0 0 14px 0;color:#a9bdd4;line-height:1.5}"
        "a{display:inline-block;padding:10px 14px;border-radius:10px;background:#17d6a5;color:#03271d;text-decoration:none;font-weight:700}"
        "</style>"
        "</head>"
        "<body>"
        "<main class='card'>"
        f"<h1>{escape(title)} Moved</h1>"
        "<p>The legacy API-served dashboard has been removed. Use the standalone Next dashboard instead.</p>"
        f"<a href='{escape(target)}' target='_blank' rel='noreferrer'>Open Dashboard</a>"
        "</main>"
        "</body>"
        "</html>"
    )
    return HTMLResponse(content=html)
