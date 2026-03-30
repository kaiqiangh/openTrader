"""Lightweight HTTP health + metrics endpoint for workers.

Uses a background daemon thread with stdlib http.server so no extra
dependencies are required (aiohttp, etc.).

Endpoints:
- GET /health — returns 200 "ok" or 503 "unhealthy"
- GET /metrics — Prometheus text exposition format (if metrics_render callback is set)
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class _ReuseHTTPServer(HTTPServer):
    """HTTPServer that allows immediate port reuse (avoids TIME_WAIT)."""

    allow_reuse_address = True


class WorkerHealthServer:
    """Minimal health-check + metrics HTTP server bound to a daemon thread.

    Usage::

        registry = PrometheusRegistry()
        server = WorkerHealthServer(port=8081, metrics_render=registry.render)
        server.start()
        ...  # worker loop
        server.stop()
    """

    def __init__(
        self,
        *,
        port: int = 8080,
        metrics_render: Callable[[], str] | None = None,
    ) -> None:
        self.port = port
        self._healthy = threading.Event()
        self._healthy.set()  # Start healthy
        self._metrics_render = metrics_render
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        healthy_event = self._healthy
        metrics_render = self._metrics_render

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 — http.server protocol
                if self.path == "/health":
                    if healthy_event.is_set():
                        self.send_response(200)
                        self.end_headers()
                        self.wfile.write(b"ok")
                    else:
                        self.send_response(503)
                        self.end_headers()
                        self.wfile.write(b"unhealthy")
                    return

                if self.path == "/metrics" and metrics_render is not None:
                    payload = metrics_render()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(payload.encode("utf-8"))
                    return

                self.send_response(404)
                self.end_headers()

            def log_message(self, _format: str, *args: object) -> None:
                pass  # Suppress per-request logs

        try:
            self._server = _ReuseHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError:
            logger.warning(
                "health_server_bind_failed port=%d — continuing without health endpoint", self.port
            )
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"health-{self.port}",
        )
        self._thread.start()
        logger.info(
            "health_server_started port=%d metrics=%s",
            self.port,
            "enabled" if metrics_render else "disabled",
        )

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()

    def set_healthy(self, healthy: bool) -> None:
        if healthy:
            self._healthy.set()
        else:
            self._healthy.clear()
