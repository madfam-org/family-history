"""Prometheus metrics, served on a separate listener (`:9090/metrics`), never on the API port."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from wsgiref.simple_server import WSGIServer

from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server

logger = logging.getLogger("family_history.metrics")

REGISTRY = CollectorRegistry(auto_describe=True)

REQUEST_DURATION = Histogram(
    "fh_http_request_duration_seconds",
    "HTTP request latency by method, route template and status.",
    labelnames=("method", "route", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
REQUESTS_TOTAL = Counter(
    "fh_http_requests_total",
    "HTTP requests by method, route template and status.",
    labelnames=("method", "route", "status"),
    registry=REGISTRY,
)
AUTH_FAILURES = Counter(
    "fh_auth_failures_total",
    "Rejected bearer tokens and early-access denials by reason code.",
    labelnames=("code",),
    registry=REGISTRY,
)
WAITLIST_SIGNUPS = Counter(
    "fh_waitlist_requests_total",
    "Waitlist submissions by outcome.",
    labelnames=("outcome",),
    registry=REGISTRY,
)


@dataclass
class MetricsServer:
    server: WSGIServer
    thread: threading.Thread

    @property
    def port(self) -> int:
        return int(self.server.server_port)

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def start_metrics_server(port: int, addr: str = "0.0.0.0") -> MetricsServer:  # noqa: S104
    """Start the metrics listener on its own port. Binding all interfaces is intended: the
    Kubernetes `family-history-api-metrics` Service scrapes it; it is never routed publicly."""
    server, thread = start_http_server(port, addr=addr, registry=REGISTRY)
    logger.info("metrics listener started", extra={"port": server.server_port})
    return MetricsServer(server=server, thread=thread)


def observe_request(method: str, route: str, status: int, seconds: float) -> None:
    labels = {"method": method, "route": route, "status": str(status)}
    REQUEST_DURATION.labels(**labels).observe(seconds)
    REQUESTS_TOTAL.labels(**labels).inc()
