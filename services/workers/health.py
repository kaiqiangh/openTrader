"""Lightweight HTTP health endpoint for workers.

Uses a background daemon thread with stdlib http.server so no extra
dependencies are required (aiohttp, etc.).
"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger(__name__)


class _ReuseHTTPServer(HTTPServer):
    """HTTPServer that allows immediate port reuse (avoids TIME_WAIT)."""

    allow_reuse_address = True


class WorkerHealthServer:
    """Minimal health-check HTTP server bound to a daemon thread.

    Usage::

        server = WorkerHealthServer(port=8081)
        server.start()
        ...  # worker loop
        server.stop()
    """

    def __init__(self, *, port: int = 8080) -> None:
        self.port = port
        self.healthy = True
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        healthy_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 — http.server protocol
                if healthy_ref.healthy:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"ok")
                else:
                    self.send_response(503)
                    self.end_headers()
                    self.wfile.write(b"unhealthy")

            def log_message(self, _format: str, *args: object) -> None:
                pass  # Suppress per-request logs

        try:
            self._server = _ReuseHTTPServer(("0.0.0.0", self.port), Handler)
        except OSError:
            logger.warning("health_server_bind_failed port=%d — continuing without health endpoint", self.port)
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name=f"health-{self.port}",
        )
        self._thread.start()
        logger.info("health_server_started port=%d", self.port)

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()

    def set_healthy(self, healthy: bool) -> None:
        self.healthy = healthy
