"""Tests for worker health server metrics endpoint."""

from __future__ import annotations

import time
import threading
import urllib.request

from services.workers.health import WorkerHealthServer
from services.shared.runtime.prometheus import PrometheusRegistry


def test_health_server_serves_metrics() -> None:
    registry = PrometheusRegistry()
    registry.inc_counter(name="test_counter", help_text="Test counter", label_values={"svc": "test"})
    registry.observe_histogram(name="test_histogram", help_text="Test histogram", value=0.5)

    server = WorkerHealthServer(port=18999, metrics_render=registry.render)
    server.start()
    try:
        # Give server a moment to bind
        time.sleep(0.1)

        # Health endpoint
        response = urllib.request.urlopen("http://127.0.0.1:18999/health", timeout=2)
        assert response.status == 200
        assert response.read() == b"ok"

        # Metrics endpoint
        response = urllib.request.urlopen("http://127.0.0.1:18999/metrics", timeout=2)
        assert response.status == 200
        body = response.read().decode("utf-8")
        assert "test_counter" in body
        assert "test_histogram" in body
        assert "text/plain" in response.headers.get("Content-Type", "")

        # 404 for unknown paths
        try:
            urllib.request.urlopen("http://127.0.0.1:18999/unknown", timeout=2)
            assert False, "Should have raised HTTPError"
        except urllib.request.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.stop()


def test_health_server_no_metrics_returns_404() -> None:
    server = WorkerHealthServer(port=18998)  # No metrics_render
    server.start()
    try:
        time.sleep(0.1)
        try:
            urllib.request.urlopen("http://127.0.0.1:18998/metrics", timeout=2)
            assert False, "Should have raised HTTPError"
        except urllib.request.HTTPError as exc:
            assert exc.code == 404
    finally:
        server.stop()
