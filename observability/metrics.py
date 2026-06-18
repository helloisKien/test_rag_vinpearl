"""DA10 — Prometheus metrics collectors (§6.2 monitoring_plan).

Import toàn bộ từ đây; không tạo metric object ở nơi khác tránh duplicate registration.
"""
from prometheus_client import Counter, Gauge, Histogram

# ── HTTP layer ────────────────────────────────────────────────────────────────

HTTP_REQUESTS = Counter(
    "da10_http_requests_total",
    "Total HTTP requests",
    ["endpoint", "method", "status"],
)

HTTP_DURATION = Histogram(
    "da10_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint"],
    buckets=[0.05, 0.1, 0.15, 0.25, 0.5, 0.75, 1.0, 2.0, 5.0],
)

SEARCH_ZERO_RESULTS = Counter(
    "da10_search_zero_results_total",
    "Search requests returning zero results",
    ["search_mode"],
)

CONTEXT_DURATION = Histogram(
    "da10_context_build_duration_seconds",
    "Context build duration in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 15.0, 30.0, 60.0, 120.0],
)

# ── Per-stage pipeline (§6.2 da10_stage_duration_seconds) ────────────────────

STAGE_DURATION = Histogram(
    "da10_stage_duration_seconds",
    "Pipeline stage duration in seconds",
    ["stage"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0, 15.0, 30.0],
)

# ── Dependency health ─────────────────────────────────────────────────────────

DEP_UP = Gauge(
    "da10_dependency_up",
    "Dependency health: 1=up, 0=down",
    ["dependency"],
)

DEP_PROBE_DURATION = Histogram(
    "da10_dependency_probe_duration_seconds",
    "Dependency probe latency in seconds",
    ["dependency"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5],
)
